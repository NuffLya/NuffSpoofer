import os
import sys
import ctypes
import winreg
import random
import string
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import json
import base64
import hashlib
import shutil
from datetime import datetime
from pathlib import Path

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def request_admin():
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, 
            f'"{os.path.abspath(__file__)}"', None, 1
        )
        sys.exit(0)

def generate_hwid(length=32):
    return ''.join(random.choices('0123456789ABCDEF', k=length))

def generate_guid():
    return '{' + '-'.join([
        generate_hwid(8),
        generate_hwid(4),
        generate_hwid(4),
        generate_hwid(4),
        generate_hwid(12)
    ]) + '}'

def generate_mac():
    mac = [random.randint(0x00, 0xFF) for _ in range(6)]
    mac[0] = (mac[0] & 0xFE) | 0x02
    return '-'.join([f'{x:02X}' for x in mac])

def generate_serial():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=20))

def generate_volume_id():
    return f"{random.randint(1000, 9999):04X}-{random.randint(1000, 9999):04X}"

class RegistryManager:
    def __init__(self, log_callback=None):
        self.log = log_callback or print
        self.backup_file = "nuffspoofer_backup.json"
        self.backup_data = {}
    
    def get_value(self, key_path, value_name, hive=winreg.HKEY_LOCAL_MACHINE):
        try:
            key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
            value, reg_type = winreg.QueryValueEx(key, value_name)
            winreg.CloseKey(key)
            return value, reg_type
        except FileNotFoundError:
            return None, None
        except Exception as e:
            self.log(f"[!] Ошибка чтения {key_path}\\{value_name}: {e}")
            return None, None
    
    def backup_value(self, key_path, value_name, hive=winreg.HKEY_LOCAL_MACHINE):
        try:
            value, reg_type = self.get_value(key_path, value_name, hive)
            if value is not None:
                hive_name = "HKLM" if hive == winreg.HKEY_LOCAL_MACHINE else "HKCU"
                backup_key = f"{hive_name}\\{key_path}\\{value_name}"
                
                if isinstance(value, bytes):
                    value_encoded = base64.b64encode(value).decode('utf-8')
                    is_binary = True
                else:
                    value_encoded = value
                    is_binary = False
                
                self.backup_data[backup_key] = {
                    "value": value_encoded,
                    "type": reg_type,
                    "hive": hive_name,
                    "is_binary": is_binary
                }
                return True
        except Exception as e:
            self.log(f"[!] Ошибка бэкапа {key_path}\\{value_name}: {e}")
        return False
    
    def save_backup(self):
        try:
            backup = {
                "timestamp": datetime.now().isoformat(),
                "version": "1.1",
                "data": self.backup_data
            }
            with open(self.backup_file, 'w', encoding='utf-8') as f:
                json.dump(backup, f, indent=4, ensure_ascii=False)
            self.log(f"[✓] Бэкап сохранён: {self.backup_file} ({len(self.backup_data)} значений)")
            return True
        except Exception as e:
            self.log(f"[!] Ошибка сохранения бэкапа: {e}")
            return False
    
    def load_backup(self):
        try:
            if not os.path.exists(self.backup_file):
                self.log("[!] Файл бэкапа не найден")
                return False
            
            with open(self.backup_file, 'r', encoding='utf-8') as f:
                backup = json.load(f)
            
            self.backup_data = backup.get("data", {})
            timestamp = backup.get("timestamp", "unknown")
            self.log(f"[✓] Бэкап загружен: {timestamp} ({len(self.backup_data)} значений)")
            return True
        except Exception as e:
            self.log(f"[!] Ошибка загрузки бэкапа: {e}")
            return False
    
    def set_value(self, key_path, value_name, value, value_type=winreg.REG_SZ, hive=winreg.HKEY_LOCAL_MACHINE):
        try:
            self.backup_value(key_path, value_name, hive)
            
            try:
                key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE)
            except FileNotFoundError:
                key = winreg.CreateKey(hive, key_path)
            
            winreg.SetValueEx(key, value_name, 0, value_type, value)
            winreg.CloseKey(key)
            
            if isinstance(value, bytes):
                display_value = f"<binary data {len(value)} bytes>"
            else:
                display_value = value if len(str(value)) < 50 else str(value)[:50] + "..."
            
            self.log(f"[✓] {key_path}\\{value_name} → {display_value}")
            return True
        except Exception as e:
            self.log(f"[!] Ошибка записи {key_path}\\{value_name}: {e}")
            return False
    
    def delete_value(self, key_path, value_name, hive=winreg.HKEY_LOCAL_MACHINE):
        try:
            self.backup_value(key_path, value_name, hive)
            key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, value_name)
            winreg.CloseKey(key)
            self.log(f"[✓] Удалено: {key_path}\\{value_name}")
            return True
        except Exception as e:
            self.log(f"[!] Ошибка удаления {key_path}\\{value_name}: {e}")
            return False
    
    def restore_from_backup(self):
        if not self.backup_data:
            self.log("[!] Нет данных для восстановления")
            return False
        
        success_count = 0
        for backup_key, data in self.backup_data.items():
            try:
                parts = backup_key.split("\\")
                hive_str = parts[0]
                value_name = parts[-1]
                key_path = "\\".join(parts[1:-1])
                
                hive = winreg.HKEY_LOCAL_MACHINE if hive_str == "HKLM" else winreg.HKEY_CURRENT_USER
                
                value = data["value"]
                if data.get("is_binary", False):
                    value = base64.b64decode(value)
                
                key = winreg.CreateKey(hive, key_path)
                winreg.SetValueEx(key, value_name, 0, data["type"], value)
                winreg.CloseKey(key)
                
                self.log(f"[✓] Восстановлено: {backup_key}")
                success_count += 1
            except Exception as e:
                self.log(f"[!] Ошибка восстановления {backup_key}: {e}")
        
        self.log(f"\n[✓] Восстановлено: {success_count}/{len(self.backup_data)} значений")
        return success_count > 0

class HWIDSpoofer:
    def __init__(self, log_callback=None):
        self.log = log_callback or print
        self.reg = RegistryManager(log_callback)
        self.spoofed_ids = {}
    
    def spoof_machine_guid(self):
        self.log("\n[*] === ПОДМЕНА MACHINE GUID ===")
        new_guid = generate_guid()
        self.spoofed_ids["MachineGuid"] = new_guid
        
        paths = [
            r"SOFTWARE\Microsoft\Cryptography",
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        ]
        
        for path in paths:
            self.reg.set_value(path, "MachineGuid", new_guid)
        
        return True
    
    def spoof_hwid_profile(self):
        self.log("\n[*] === ПОДМЕНА HWID PROFILE ===")
        new_hwid = generate_guid()
        self.spoofed_ids["HwProfileGuid"] = new_hwid
        
        path = r"SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\0001"
        return self.reg.set_value(path, "HwProfileGuid", new_hwid)
    
    def spoof_system_info(self):
        self.log("\n[*] === ПОДМЕНА СИСТЕМНОЙ ИНФОРМАЦИИ ===")
        
        path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
        
        new_product_id = '-'.join([
            str(random.randint(10000, 99999)) for _ in range(5)
        ])
        self.reg.set_value(path, "ProductId", new_product_id)
        self.spoofed_ids["ProductId"] = new_product_id
        
        new_digital_id = bytes([random.randint(0, 255) for _ in range(164)])
        self.reg.set_value(path, "DigitalProductId", new_digital_id, winreg.REG_BINARY)
        
        new_install_date = random.randint(1500000000, 1700000000)
        self.reg.set_value(path, "InstallDate", new_install_date, winreg.REG_DWORD)
        
        return True
    
    def spoof_mac_addresses(self):
        self.log("\n[*] === ПОДМЕНА MAC-АДРЕСОВ ===")
        
        base_path = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}"
        spoofed_count = 0
        
        for i in range(30):
            try:
                key_path = f"{base_path}\\{i:04d}"
                test_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ)
                winreg.CloseKey(test_key)
                
                new_mac = generate_mac()
                if self.reg.set_value(key_path, "NetworkAddress", new_mac.replace('-', '')):
                    spoofed_count += 1
            except FileNotFoundError:
                continue
            except Exception:
                continue
        
        self.log(f"[✓] Подменено MAC-адресов: {spoofed_count}")
        return spoofed_count > 0
    
    def spoof_disk_serials(self):
        self.log("\n[*] === ПОДМЕНА DISK SERIALS ===")
        
        spoofed_count = 0
        
        disk_models = [
            "Samsung SSD 980 PRO 1TB",
            "WD Black SN850X 1TB",
            "Kingston KC3000 1024GB",
            "Crucial P5 Plus 1TB",
            "Seagate FireCuda 530 1TB"
        ]
        
        try:
            base_paths = [
                r"SYSTEM\CurrentControlSet\Enum\SCSI",
                r"SYSTEM\CurrentControlSet\Enum\IDE",
                r"SYSTEM\CurrentControlSet\Enum\NVME"
            ]
            
            for base_path in base_paths:
                try:
                    base_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path, 0, winreg.KEY_READ)
                    i = 0
                    while True:
                        try:
                            disk_key_name = winreg.EnumKey(base_key, i)
                            disk_path = f"{base_path}\\{disk_key_name}"
                            
                            sub_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, disk_path, 0, winreg.KEY_READ)
                            j = 0
                            while True:
                                try:
                                    instance_name = winreg.EnumKey(sub_key, j)
                                    instance_path = f"{disk_path}\\{instance_name}"
                                    
                                    new_serial = ''.join(random.choices(string.ascii_uppercase + string.digits + '_', k=20))
                                    new_model = random.choice(disk_models)
                                    
                                    if self.reg.set_value(instance_path, "SerialNumber", new_serial):
                                        spoofed_count += 1
                                    
                                    device_desc = f"Disk drive - {new_model}"
                                    self.reg.set_value(instance_path, "DeviceDesc", device_desc)
                                    self.reg.set_value(instance_path, "FriendlyName", new_model)
                                    
                                    device_params_path = f"{instance_path}\\Device Parameters"
                                    try:
                                        test_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, device_params_path, 0, winreg.KEY_READ)
                                        winreg.CloseKey(test_key)
                                        self.reg.set_value(device_params_path, "SerialNumber", new_serial)
                                    except FileNotFoundError:
                                        pass
                                    
                                    j += 1
                                except OSError:
                                    break
                            winreg.CloseKey(sub_key)
                            i += 1
                        except OSError:
                            break
                    winreg.CloseKey(base_key)
                except FileNotFoundError:
                    continue
            
            scsi_ports_path = r"HARDWARE\DEVICEMAP\Scsi"
            try:
                scsi_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, scsi_ports_path, 0, winreg.KEY_READ)
                i = 0
                while True:
                    try:
                        port_name = winreg.EnumKey(scsi_key, i)
                        port_path = f"{scsi_ports_path}\\{port_name}\\Scsi Bus 0"
                        
                        sub_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, port_path, 0, winreg.KEY_READ)
                        j = 0
                        while True:
                            try:
                                target_name = winreg.EnumKey(sub_key, j)
                                target_path = f"{port_path}\\{target_name}"
                                
                                new_serial = ''.join(random.choices(string.ascii_uppercase + string.digits, k=20))
                                new_model = random.choice(disk_models)
                                
                                self.reg.set_value(target_path, "SerialNumber", new_serial, hive=winreg.HKEY_LOCAL_MACHINE)
                                self.reg.set_value(target_path, "Identifier", new_model, hive=winreg.HKEY_LOCAL_MACHINE)
                                
                                j += 1
                            except OSError:
                                break
                        winreg.CloseKey(sub_key)
                        i += 1
                    except (OSError, FileNotFoundError):
                        break
                winreg.CloseKey(scsi_key)
            except FileNotFoundError:
                pass
            
            storage_path = r"SYSTEM\CurrentControlSet\Services\disk\Enum"
            try:
                storage_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, storage_path, 0, winreg.KEY_READ)
                i = 0
                while True:
                    try:
                        value_name = str(i)
                        value, _ = winreg.QueryValueEx(storage_key, value_name)
                        
                        parts = value.split('\\')
                        if len(parts) >= 3:
                            new_serial = generate_hwid(16)
                            parts[-1] = new_serial
                            new_value = '\\'.join(parts)
                            self.reg.set_value(storage_path, value_name, new_value)
                        
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(storage_key)
            except FileNotFoundError:
                pass
            
            self.log(f"[✓] Подменено дисковых идентификаторов: {spoofed_count}")
            return spoofed_count > 0
            
        except Exception as e:
            self.log(f"[!] Ошибка подмены дисков: {e}")
            return False
    
    def spoof_smbios(self):
        self.log("\n[*] === ПОДМЕНА SMBIOS ===")
        
        path = r"SYSTEM\CurrentControlSet\Control\SystemInformation"
        
        fake_manufacturer = random.choice(["ASUS", "Gigabyte", "MSI", "ASRock"])
        fake_product = f"{fake_manufacturer}-{generate_hwid(8)}"
        fake_version = f"v{random.randint(1, 9)}.{random.randint(0, 9)}"
        
        self.reg.set_value(path, "SystemManufacturer", fake_manufacturer)
        self.reg.set_value(path, "SystemProductName", fake_product)
        self.reg.set_value(path, "BIOSVersion", fake_version)
        
        self.spoofed_ids["SystemProduct"] = fake_product
        return True
    
    def clean_anticheat_traces(self):
        self.log("\n[*] === ОЧИСТКА АНТИЧИТ СЛЕДОВ ===")
        
        anticheat_paths = [
            os.path.expandvars(r"%PROGRAMDATA%\EasyAntiCheat"),
            os.path.expandvars(r"%LOCALAPPDATA%\EasyAntiCheat"),
            os.path.expandvars(r"%PROGRAMDATA%\BattlEye"),
            os.path.expandvars(r"%APPDATA%\BattlEye"),
            os.path.expandvars(r"%LOCALAPPDATA%\Riot Games"),
        ]
        
        cleaned = 0
        for path in anticheat_paths:
            if os.path.exists(path):
                try:
                    shutil.rmtree(path)
                    self.log(f"[✓] Удалено: {path}")
                    cleaned += 1
                except Exception as e:
                    self.log(f"[!] Не удалось удалить {path}: {e}")
        
        reg_paths = [
            r"SOFTWARE\EasyAntiCheat",
            r"SOFTWARE\BattlEye",
            r"SOFTWARE\Riot Games",
        ]
        
        for reg_path in reg_paths:
            try:
                winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
                self.log(f"[✓] Удалён ключ реестра: {reg_path}")
                cleaned += 1
            except FileNotFoundError:
                pass
            except Exception:
                pass
        
        self.log(f"[✓] Очищено элементов: {cleaned}")
        return cleaned > 0
    
    def clean_system_traces(self):
        self.log("\n[*] === ОЧИСТКА СИСТЕМНЫХ СЛЕДОВ ===")
        
        recent_paths = [
            os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Recent"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Explorer\RecentDocs"),
        ]
        
        for path in recent_paths:
            if os.path.exists(path):
                try:
                    for file in Path(path).iterdir():
                        if file.is_file():
                            file.unlink()
                    self.log(f"[✓] Очищено: {path}")
                except Exception as e:
                    self.log(f"[!] Ошибка очистки {path}: {e}")
        
        reg_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\RecentDocs"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_WRITE)
            try:
                i = 0
                while True:
                    subkey_name = winreg.EnumKey(key, i)
                    winreg.DeleteKey(key, subkey_name)
            except OSError:
                pass
            winreg.CloseKey(key)
            self.log("[✓] Реестр RecentDocs очищен")
        except Exception as e:
            self.log(f"[!] Ошибка очистки RecentDocs: {e}")
        
        return True
    
    def spoof_full(self, options=None):
        self.log("\n" + "=" * 60)
        self.log("[*] ЗАПУСК ПОЛНОЙ ПОДМЕНЫ HWID v1.1")
        self.log("=" * 60)
        
        if options is None:
            options = {
                "machine_guid": True,
                "hwid_profile": True,
                "system_info": True,
                "mac_addresses": True,
                "disk_serials": True,
                "smbios": True,
                "clean_anticheat": True,
                "clean_traces": True,
            }
        
        success = True
        
        try:
            if options.get("machine_guid", True):
                success &= self.spoof_machine_guid()
            
            if options.get("hwid_profile", True):
                success &= self.spoof_hwid_profile()
            
            if options.get("system_info", True):
                success &= self.spoof_system_info()
            
            if options.get("mac_addresses", True):
                success &= self.spoof_mac_addresses()
            
            if options.get("disk_serials", False):
                success &= self.spoof_disk_serials()
            
            if options.get("smbios", True):
                success &= self.spoof_smbios()
            
            if options.get("clean_anticheat", True):
                self.clean_anticheat_traces()
            
            if options.get("clean_traces", True):
                self.clean_system_traces()
            
            self.reg.save_backup()
            
            self.log("\n" + "=" * 60)
            self.log("[✓] ПОДМЕНА ЗАВЕРШЕНА УСПЕШНО!")
            self.log("[!] ТРЕБУЕТСЯ ПЕРЕЗАГРУЗКА СИСТЕМЫ!")
            self.log("=" * 60)
            
            return True
        except Exception as e:
            self.log(f"\n[!] КРИТИЧЕСКАЯ ОШИБКА: {e}")
            return False
    
    def restore(self):
        self.log("\n" + "=" * 60)
        self.log("[*] ВОССТАНОВЛЕНИЕ ИЗ БЭКАПА")
        self.log("=" * 60)
        
        if self.reg.load_backup():
            return self.reg.restore_from_backup()
        return False
    
    def get_current_hwid_info(self):
        info = {}
        
        try:
            value, _ = self.reg.get_value(r"SOFTWARE\Microsoft\Cryptography", "MachineGuid")
            info["MachineGuid"] = value or "N/A"
            
            value, _ = self.reg.get_value(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "ProductId")
            info["ProductId"] = value or "N/A"
            
            value, _ = self.reg.get_value(r"SYSTEM\CurrentControlSet\Control\SystemInformation", "SystemProductName")
            info["SystemProduct"] = value or "N/A"
            
        except Exception as e:
            self.log(f"[!] Ошибка чтения HWID: {e}")
        
        return info

class HWIDSpooferGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("NuffSpoofer v1.1 by NuffLya")
        self.root.geometry("850x650")
        self.root.resizable(False, False)
        self.root.configure(bg="#1a1a1a")
        
        if not is_admin():
            messagebox.showerror(
                "Ошибка доступа",
                "Требуются права администратора!\n\n"
                "Запустите программу от имени администратора."
            )
            self.root.destroy()
            return
        
        self.spoofer = HWIDSpoofer(log_callback=self.log)
        self.create_widgets()
        self.load_current_hwid()
    
    def create_widgets(self):
        header = tk.Frame(self.root, bg="#0d0d0d", height=70)
        header.pack(fill=tk.X)
        
        title = tk.Label(
            header, 
            text="⚡ NUFFSPOOFER v1.1 ⚡",
            font=("Consolas", 22, "bold"),
            fg="#00ff41", bg="#0d0d0d"
        )
        title.pack(pady=15)
        
        subtitle = tk.Label(
            header,
            text="Системная подмена HWID | Автоматический бэкап | Очистка античитов",
            font=("Consolas", 9),
            fg="#888888", bg="#0d0d0d"
        )
        subtitle.pack()
        
        info_frame = tk.LabelFrame(
            self.root,
            text="Текущий HWID",
            font=("Consolas", 10, "bold"),
            bg="#1a1a1a", fg="#00ff41",
            bd=2, relief=tk.GROOVE
        )
        info_frame.pack(padx=10, pady=10, fill=tk.X)
        
        self.hwid_info_text = tk.Text(
            info_frame,
            height=4,
            font=("Consolas", 9),
            bg="#0d0d0d", fg="#00ff41",
            insertbackground="#00ff41",
            wrap=tk.WORD,
            state=tk.DISABLED
        )
        self.hwid_info_text.pack(padx=5, pady=5, fill=tk.X)
        
        options_frame = tk.LabelFrame(
            self.root,
            text="Параметры подмены",
            font=("Consolas", 10, "bold"),
            bg="#1a1a1a", fg="#00ff41",
            bd=2, relief=tk.GROOVE
        )
        options_frame.pack(padx=10, pady=5, fill=tk.X)
        
        options_inner = tk.Frame(options_frame, bg="#1a1a1a")
        options_inner.pack(padx=10, pady=5)
        
        left_col = tk.Frame(options_inner, bg="#1a1a1a")
        left_col.grid(row=0, column=0, sticky=tk.W, padx=10)
        
        self.opt_machine_guid = tk.BooleanVar(value=True)
        self.opt_hwid_profile = tk.BooleanVar(value=True)
        self.opt_system_info = tk.BooleanVar(value=True)
        self.opt_mac = tk.BooleanVar(value=True)
        
        tk.Checkbutton(
            left_col, text="✓ Machine GUID (основной ID)",
            variable=self.opt_machine_guid,
            font=("Consolas", 9), bg="#1a1a1a", fg="#ffffff",
            selectcolor="#0d0d0d", activebackground="#1a1a1a"
        ).pack(anchor=tk.W)
        
        tk.Checkbutton(
            left_col, text="✓ HWID Profile",
            variable=self.opt_hwid_profile,
            font=("Consolas", 9), bg="#1a1a1a", fg="#ffffff",
            selectcolor="#0d0d0d", activebackground="#1a1a1a"
        ).pack(anchor=tk.W)
        
        tk.Checkbutton(
            left_col, text="✓ System Info (ProductID, BIOS)",
            variable=self.opt_system_info,
            font=("Consolas", 9), bg="#1a1a1a", fg="#ffffff",
            selectcolor="#0d0d0d", activebackground="#1a1a1a"
        ).pack(anchor=tk.W)
        
        tk.Checkbutton(
            left_col, text="✓ MAC Addresses",
            variable=self.opt_mac,
            font=("Consolas", 9), bg="#1a1a1a", fg="#ffffff",
            selectcolor="#0d0d0d", activebackground="#1a1a1a"
        ).pack(anchor=tk.W)
        
        right_col = tk.Frame(options_inner, bg="#1a1a1a")
        right_col.grid(row=0, column=1, sticky=tk.W, padx=10)
        
        self.opt_disk = tk.BooleanVar(value=True)
        self.opt_smbios = tk.BooleanVar(value=True)
        self.opt_clean_ac = tk.BooleanVar(value=True)
        self.opt_clean_traces = tk.BooleanVar(value=True)
        
        tk.Checkbutton(
            right_col, text="✓ Disk Serials (модель, серийник)",
            variable=self.opt_disk,
            font=("Consolas", 9), bg="#1a1a1a", fg="#ffffff",
            selectcolor="#0d0d0d", activebackground="#1a1a1a"
        ).pack(anchor=tk.W)
        
        tk.Checkbutton(
            right_col, text="✓ SMBIOS (Motherboard)",
            variable=self.opt_smbios,
            font=("Consolas", 9), bg="#1a1a1a", fg="#ffffff",
            selectcolor="#0d0d0d", activebackground="#1a1a1a"
        ).pack(anchor=tk.W)
        
        tk.Checkbutton(
            right_col, text="✓ Очистка античитов (EAC/BE)",
            variable=self.opt_clean_ac,
            font=("Consolas", 9), bg="#1a1a1a", fg="#ffffff",
            selectcolor="#0d0d0d", activebackground="#1a1a1a"
        ).pack(anchor=tk.W)
        
        tk.Checkbutton(
            right_col, text="✓ Очистка системных следов",
            variable=self.opt_clean_traces,
            font=("Consolas", 9), bg="#1a1a1a", fg="#ffffff",
            selectcolor="#0d0d0d", activebackground="#1a1a1a"
        ).pack(anchor=tk.W)
        
        btn_frame = tk.Frame(self.root, bg="#1a1a1a")
        btn_frame.pack(pady=10)
        
        self.spoof_btn = tk.Button(
            btn_frame,
            text="🚀 ПОДМЕНИТЬ HWID",
            command=self.run_spoof,
            font=("Consolas", 13, "bold"),
            bg="#00aa00", fg="white",
            width=22, height=2,
            relief=tk.RAISED, bd=3,
            activebackground="#00dd00"
        )
        self.spoof_btn.grid(row=0, column=0, padx=5)
        
        self.restore_btn = tk.Button(
            btn_frame,
            text="⚠️ ВОССТАНОВИТЬ",
            command=self.run_restore,
            font=("Consolas", 13, "bold"),
            bg="#ff6600", fg="white",
            width=22, height=2,
            relief=tk.RAISED, bd=3,
            activebackground="#ff8800"
        )
        self.restore_btn.grid(row=0, column=1, padx=5)
        
        log_frame = tk.LabelFrame(
            self.root,
            text="Лог операций",
            font=("Consolas", 10, "bold"),
            bg="#1a1a1a", fg="#00ff41",
            bd=2, relief=tk.GROOVE
        )
        log_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            font=("Consolas", 9),
            bg="#0d0d0d", fg="#00ff41",
            insertbackground="#00ff41",
            wrap=tk.WORD
        )
        self.log_text.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)
        
        self.status_bar = tk.Label(
            self.root,
            text="✓ Готов к работе | Права администратора: ОК",
            font=("Consolas", 9, "bold"),
            bg="#0d0d0d", fg="#00ff41",
            anchor=tk.W, relief=tk.SUNKEN
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.log("=" * 80)
        self.log("NuffSpoofer v1.1")
        self.log("Автор: NuffLya | Права администратора: ✓")
        self.log("=" * 80)
    
    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def load_current_hwid(self):
        info = self.spoofer.get_current_hwid_info()
        
        self.hwid_info_text.config(state=tk.NORMAL)
        self.hwid_info_text.delete(1.0, tk.END)
        
        text = f"Machine GUID: {info.get('MachineGuid', 'N/A')}\n"
        text += f"Product ID: {info.get('ProductId', 'N/A')}\n"
        text += f"System Product: {info.get('SystemProduct', 'N/A')}"
        
        self.hwid_info_text.insert(1.0, text)
        self.hwid_info_text.config(state=tk.DISABLED)
    
    def run_spoof(self):
        confirm = messagebox.askyesno(
            "Подтверждение",
            "Подменить HWID системы?\n\n"
            "• Будет создана резервная копия\n"
            "• После подмены требуется перезагрузка\n"
            "• Все выбранные параметры будут изменены\n\n"
            "Продолжить?"
        )
        
        if not confirm:
            return
        
        self.spoof_btn.config(state=tk.DISABLED)
        self.restore_btn.config(state=tk.DISABLED)
        self.status_bar.config(text="⏳ Выполняется подмена HWID...", fg="#ffaa00")
        
        def spoof_thread():
            options = {
                "machine_guid": self.opt_machine_guid.get(),
                "hwid_profile": self.opt_hwid_profile.get(),
                "system_info": self.opt_system_info.get(),
                "mac_addresses": self.opt_mac.get(),
                "disk_serials": self.opt_disk.get(),
                "smbios": self.opt_smbios.get(),
                "clean_anticheat": self.opt_clean_ac.get(),
                "clean_traces": self.opt_clean_traces.get(),
            }
            
            success = self.spoofer.spoof_full(options)
            
            self.spoof_btn.config(state=tk.NORMAL)
            self.restore_btn.config(state=tk.NORMAL)
            
            if success:
                self.status_bar.config(
                    text="✓ Подмена завершена! Перезагрузите систему.",
                    fg="#00ff41"
                )
                messagebox.showinfo(
                    "Успешно",
                    "HWID успешно подменён!\n\n"
                    "Рекомендуется перезагрузить систему для применения всех изменений."
                )
                self.load_current_hwid()
            else:
                self.status_bar.config(text="✗ Ошибка подмены", fg="#ff0000")
                messagebox.showerror("Ошибка", "Произошла ошибка при подмене HWID.\nПроверьте лог.")
        
        threading.Thread(target=spoof_thread, daemon=True).start()
    
    def run_restore(self):
        confirm = messagebox.askyesno(
            "Подтверждение",
            "Восстановить оригинальные значения HWID из бэкапа?\n\n"
            "Это отменит все изменения, сделанные спуфером."
        )
        
        if not confirm:
            return
        
        self.spoof_btn.config(state=tk.DISABLED)
        self.restore_btn.config(state=tk.DISABLED)
        self.status_bar.config(text="⏳ Восстановление из бэкапа...", fg="#ffaa00")
        
        def restore_thread():
            success = self.spoofer.restore()
            
            self.spoof_btn.config(state=tk.NORMAL)
            self.restore_btn.config(state=tk.NORMAL)
            
            if success:
                self.status_bar.config(text="✓ Восстановление завершено", fg="#00ff41")
                messagebox.showinfo("Успешно", "HWID восстановлён из бэкапа!")
                self.load_current_hwid()
            else:
                self.status_bar.config(text="✗ Ошибка восстановления", fg="#ff0000")
                messagebox.showerror("Ошибка", "Файл бэкапа не найден или повреждён.")
        
        threading.Thread(target=restore_thread, daemon=True).start()

def main():
    request_admin()
    root = tk.Tk()
    app = HWIDSpooferGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
