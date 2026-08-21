"""
Script Automatizado de Publicacion Local y Release en GitHub:
1. Ejecuta la suite de pruebas unitarias en local (offscreen).
2. Compila el ejecutable nativo (.exe) con PyInstaller y crea el ZIP.
3. Sube la Release directamente a GitHub Releases mediante la API REST.
"""

import os
import sys
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
DEFAULT_TAG = "v1.0.0"

def run_local_tests() -> bool:
    print("\n" + "=" * 60)
    print(" [TESTS] 1. EJECUTANDO PRUEBAS EN SEGUNDO PLANO (OFFSCREEN)")
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

def build_executable_and_zip(zip_path: str, force_rebuild: bool = False) -> bool:
    print("\n" + "=" * 60)
    print(" [BUILD] 2. COMPILANDO EJECUTABLE Y CREANDO ARCHIVO ZIP")
    print("=" * 60)
    
    if os.path.exists(zip_path) and not force_rebuild:
        size_mb = os.path.getsize(zip_path) / (1024 * 1024)
        print(f"[OK] Archivo ZIP existente detectado: '{zip_path}' ({size_mb:.1f} MB). Usando paquete listo.")
        return True

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
        
    dist_folder = os.path.join("dist", "TapoC225_BabyMonitor")
    if not os.path.exists(dist_folder):
        print(f"[ERROR] No se encontro la carpeta compilada '{dist_folder}'.")
        return False
        
    # 3. Comprimir a ZIP con compresión máxima (ZIP_DEFLATED nivel 9)
    print(f"[*] Comprimiendo '{dist_folder}' en '{zip_path}' con compresión máxima...")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(dist_folder):
            for f in files:
                fp = os.path.join(root, f)
                arcname = os.path.relpath(fp, "dist")
                zf.write(fp, arcname)
    
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"[OK] Archivo ZIP ultra-comprimido generado exitosamente: {zip_path} ({size_mb:.1f} MB)")
    return True

def upload_to_github_release(tag_name: str, zip_path: str, token: str) -> bool:
    print("\n" + "=" * 60)
    print(f" [RELEASE] 3. PUBLICANDO RELEASE '{tag_name}' DIRECTAMENTE EN GITHUB")
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
    upload_url = upload_url_template.split("{")[0] + f"?name={os.path.basename(zip_path)}"
    upload_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/zip"
    }
    
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"[*] Subiendo '{zip_path}' ({size_mb:.1f} MB) a GitHub Releases (esto tomara unos segundos)...")
    with open(zip_path, "rb") as f:
        file_data = f.read()
        
    upload_res = requests.post(upload_url, data=file_data, headers=upload_headers)
    if upload_res.status_code in (200, 201):
        print(f"\n[EXITO TOTAL] Release publicada con binario descargable en:")
        print(f"-> https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/tag/{tag_name}")
        return True
    else:
        print(f"[ERROR] Error al subir el binario: {upload_res.status_code} - {upload_res.text}")
        return False

def main():
    tag_name = DEFAULT_TAG
    force_rebuild = False
    
    for arg in sys.argv[1:]:
        if arg.startswith("v"):
            tag_name = arg
        elif arg == "--rebuild":
            force_rebuild = True

    zip_path = "TapoC225_BabyMonitor_Windows.zip"
    
    print(f"Iniciando pipeline de publicacion local para tag: {tag_name}")
    
    # 1. Tests locales (offscreen)
    if not run_local_tests():
        return
        
    # 2. Compilar
    if not build_executable_and_zip(zip_path, force_rebuild=force_rebuild):
        return
        
    # 3. Token de GitHub
    token = os.environ.get("GITHUB_TOKEN")
    if not token and os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GITHUB_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
                        
    if not token:
        print("\n[!] Ingresa tu GitHub Personal Access Token (PAT) para subir la release directamente:")
        token = input("GITHUB_TOKEN: ").strip()
        
    if not token:
        print("[ERROR] No se proporciono token de GitHub. El archivo ZIP local esta listo en la raiz.")
        return
        
    # 4. Subir Release
    upload_to_github_release(tag_name, zip_path, token)

if __name__ == "__main__":
    main()
