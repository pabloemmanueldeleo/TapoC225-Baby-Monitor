"""
Script Automatizado de Publicacion Local y Release en GitHub:
1. Ejecuta la suite de pruebas unitarias en local (offscreen).
2. Compila el ejecutable nativo (.exe) con PyInstaller.
3. Realiza prueba End-to-End obligatoria (Smoke-Test) del .exe compilado.
4. Genera el paquete ZIP ultra-comprimido.
5. Sube la Release directamente a GitHub Releases mediante la API REST.
"""

import os
import sys
import time
import shutil
import zipfile
import subprocess
import requests

# Forzar UTF-8 en salida si esta disponible
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_OWNER = "pabloemmanueldeleo"
REPO_NAME = "TapoC225-Baby-Monitor"
DEFAULT_TAG = "v1.0.4"

def run_local_tests() -> bool:
    print("\n" + "=" * 60)
    print(" [TESTS] 1. EJECUTANDO PRUEBAS UNITARIAS (OFFSCREEN)")
    print("=" * 60)
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"]
    res = subprocess.run(cmd, env=env)
    if res.returncode != 0:
        print("\n[ERROR] Algunas pruebas fallaron. Corrige los errores antes de publicar.")
        return False
    print("[OK] Todas las pruebas unitarias pasaron con exito al 100%.")
    return True

def verify_executable_e2e(exe_path: str) -> bool:
    print("\n" + "=" * 60)
    print(" [VERIFY] 3. VERIFICACION END-TO-END DEL .EXE COMPILADO")
    print("=" * 60)
    if not os.path.exists(exe_path):
        print(f"[ERROR] No se encontro el ejecutable en '{exe_path}'.")
        return False

    exe_dir = os.path.dirname(exe_path)
    crash_log = os.path.join(exe_dir, "crash_log.txt")
    if os.path.exists(crash_log):
        try:
            os.remove(crash_log)
        except Exception:
            pass

    print(f"[*] Probando ejecucion en vivo de '{exe_path}' (--smoke-test)...")
    start_t = time.time()
    try:
        proc = subprocess.Popen(
            [exe_path, "--smoke-test"],
            cwd=exe_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        returncode = proc.wait(timeout=15)
        duration = time.time() - start_t
        print(f"[*] Proceso finalizado en {duration:.2f}s con codigo de retorno: {returncode}")

        if os.path.exists(crash_log):
            with open(crash_log, "r", encoding="utf-8", errors="replace") as f:
                log_content = f.read()
            print(f"[ERROR] Se genero un crash_log.txt durante la ejecucion:\n{log_content}")
            return False

        if returncode != 0:
            print(f"[ERROR] El ejecutable retorno codigo de error {returncode}.")
            return False

        print("[OK] El ejecutable (.exe) paso la prueba de apertura e inicializacion con exito.")
        return True
    except subprocess.TimeoutExpired:
        print("[ERROR] El ejecutable se colgo durante la prueba de apertura (timeout 20s).")
        return False
    except Exception as e:
        print(f"[ERROR] Error inesperado al verificar ejecutable: {e}")
        return False

def build_executable_and_zip(zip_path: str, force_rebuild: bool = False) -> bool:
    print("\n" + "=" * 60)
    print(" [BUILD] 2. COMPILANDO EJECUTABLE CON PYINSTALLER")
    print("=" * 60)
    
    dist_folder = os.path.join("dist", "TapoC225_BabyMonitor")
    exe_path = os.path.join(dist_folder, "TapoC225_BabyMonitor.exe")

    if not os.path.exists(exe_path) or force_rebuild:
        # 1. Asegurar exportacion de modelo ONNX
        onnx_path = "yolov8n-seg.onnx"
        if not os.path.exists(onnx_path):
            print("[*] Exportando modelo YOLOv8n a ONNX...")
            from ultralytics import YOLO
            model = YOLO("yolov8n-seg.pt")
            model.export(format="onnx", imgsz=640, simplify=True)
        
        # 2. Ejecutar PyInstaller
        cmd_build = [sys.executable, "scripts/build_exe.py"]
        res = subprocess.run(cmd_build)
        if res.returncode != 0:
            print("[ERROR] La compilacion de PyInstaller fallo.")
            return False
            
    if not os.path.exists(dist_folder) or not os.path.exists(exe_path):
        print(f"[ERROR] No se encontro la carpeta compilada o el .exe en '{dist_folder}'.")
        return False

    # 3. VERIFICACION OBLIGATORIA DEL .EXE ANTES DE ZIPEARY PUBLICAR
    if not verify_executable_e2e(exe_path):
        print("[ERROR] La prueba de ejecucion del .exe fallo. Se cancela la publicacion.")
        return False

    # 4. Comprimir a ZIP con compresión máxima (ZIP_DEFLATED nivel 9)
    print(f"\n[*] Comprimiendo '{dist_folder}' en '{zip_path}' con compresión máxima...")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(dist_folder):
            for f in files:
                fp = os.path.join(root, f)
                arcname = os.path.relpath(fp, "dist")
                zf.write(fp, arcname)
    
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"[OK] Archivo ZIP ultra-comprimido generado exitosamente: {zip_path} ({size_mb:.1f} MB)")

    # Sincronizar carpeta de prueba de Windows C:\TapoC225_BabyMonitor
    user_test_dir = r"C:\TapoC225_BabyMonitor"
    try:
        if os.path.exists(user_test_dir):
            shutil.rmtree(user_test_dir, ignore_errors=True)
        shutil.copytree(dist_folder, user_test_dir)
        print(f"[OK] Distribución actualizada en carpeta local: {user_test_dir}")
    except Exception as e:
        print(f"[WARN] No se pudo sincronizar con {user_test_dir}: {e}")

    return True

def upload_to_github_release(tag_name: str, zip_path: str, token: str) -> bool:
    print("\n" + "=" * 60)
    print(f" [RELEASE] 4. PUBLICANDO RELEASE '{tag_name}' DIRECTAMENTE EN GITHUB")
    print("=" * 60)
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # 1. Verificar o crear la Release
    release_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases"
    res = requests.get(release_url, headers=headers)
    
    release_id = None
    upload_url_template = None
    
    if res.status_code == 200:
        releases = res.json()
        for r in releases:
            if r.get("tag_name") == tag_name:
                release_id = r.get("id")
                upload_url_template = r.get("upload_url")
                print(f"[*] Release existente encontrada para el tag '{tag_name}' (ID: {release_id}).")
                break
    elif res.status_code in (401, 403):
        print(f"[ERROR] Token invalido o sin permisos: {res.status_code} - {res.text}")
        return False
                
    if not release_id:
        print(f"[*] Creando nueva Release en GitHub para el tag '{tag_name}'...")
        payload = {
            "tag_name": tag_name,
            "name": f"Release {tag_name} - TapoC225 AI Baby Monitor & Sleep Analytics",
            "body": "### TapoC225 AI Baby Monitor — Official Standalone Windows Release\n\n* **Ejecutable nativo para Windows (64-bit)** listo para usar (no requiere Python).\n* **100% Privado (Edge AI)**: todo el procesamiento corre en tu red local sin suscripciones ni nube.\n* **Incluye**: Deteccion YOLOv8n-seg, filtrado de sabanas y adultos, monitor de audio y panel de sueno pediatrico con Matplotlib.",
            "draft": False,
            "prerelease": False
        }
        create_res = requests.post(release_url, json=payload, headers=headers)
        if create_res.status_code not in (200, 201):
            print(f"[ERROR] No se pudo crear la release: {create_res.status_code} - {create_res.text}")
            return False
        rel_data = create_res.json()
        release_id = rel_data.get("id")
        upload_url_template = rel_data.get("upload_url")
        print(f"[OK] Release creada con exito (ID: {release_id}).")
        
    # 2. Verificar y eliminar asset duplicado si ya existia en esa release
    assets_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/{release_id}/assets"
    assets_res = requests.get(assets_url, headers=headers)
    if assets_res.status_code == 200:
        for asset in assets_res.json():
            if asset.get("name") == os.path.basename(zip_path):
                asset_id = asset.get("id")
                print(f"[*] Reemplazando asset previo '{asset.get('name')}' (ID: {asset_id})...")
                requests.delete(f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/assets/{asset_id}", headers=headers)

    # 3. Subir el binario ZIP como asset
    if not upload_url_template:
        print("[ERROR] No se obtuvo URL de subida de assets.")
        return False
        
    upload_url = upload_url_template.split("{")[0] + f"?name={os.path.basename(zip_path)}"
    
    headers["Content-Type"] = "application/zip"
    file_size = os.path.getsize(zip_path)
    print(f"[*] Subiendo '{zip_path}' ({file_size / (1024*1024):.1f} MB) a GitHub...")
    
    with open(zip_path, "rb") as f:
        up_res = requests.post(upload_url, headers=headers, data=f)
        
    if up_res.status_code in (200, 201):
        print(f"\n[OK] Release {tag_name} publicada exitosamente en:")
        print(f"     https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/tag/{tag_name}")
        return True
    else:
        print(f"[ERROR] Fallo al subir el binario: {up_res.status_code} - {up_res.text}")
        return False

def get_github_token() -> str:
    from dotenv import load_dotenv
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        try:
            gh_token_cmd = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
            if gh_token_cmd.returncode == 0:
                token = gh_token_cmd.stdout.strip()
        except Exception:
            pass
    return token

def get_project_version() -> str:
    try:
        with open("pyproject.toml", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("version ="):
                    v = line.split("=")[1].strip().strip('"').strip("'")
                    return "v" + v.lstrip("v")
    except Exception:
        pass
    return DEFAULT_TAG

def main():
    tag_name = get_project_version()
    force_rebuild = False
    
    for arg in sys.argv[1:]:
        if arg.startswith("v"):
            tag_name = arg
        elif arg == "--rebuild":
            force_rebuild = True

    zip_path = "TapoC225_BabyMonitor_Windows.zip"
    
    print(f"Iniciando pipeline de publicacion local para version/tag: {tag_name}")
    
    # 1. Tests locales (offscreen)
    if not run_local_tests():
        return
        
    # 2. Compilar, Verificar E2E y Empaquetar
    if not build_executable_and_zip(zip_path, force_rebuild=force_rebuild):
        return
        
    # 3. Token de GitHub
    token = get_github_token()
    if not token:
        print("\n[!] Ingresa tu GitHub Personal Access Token (PAT) para subir la release directamente:")
        token = input("GITHUB_TOKEN: ").strip()
        
    if not token:
        print("[ERROR] No se proporciono token de GitHub. El archivo ZIP local esta listo y verificado.")
        return
        
    # 4. Asegurar tag en git
    try:
        subprocess.run(["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "push", "origin", tag_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    # 5. Subir Release a GitHub
    upload_to_github_release(tag_name, zip_path, token)

if __name__ == "__main__":
    main()
