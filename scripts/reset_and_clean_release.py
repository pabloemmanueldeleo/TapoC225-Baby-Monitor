"""
Script para reiniciar completamente el repositorio:
1. Ejecuta la suite de pruebas unitarias.
2. Compila el ejecutable nativo actualizado (.exe) con PyInstaller y crea el ZIP optimizado.
3. Elimina todas las Releases viejas y sus tags de GitHub.
4. Unifica todo el historial local en UN SOLO commit raiz limpio.
5. Sube el commit limpio a origin main (force push).
6. Crea el tag v1.0.0 y publica la Release oficial con el binario ZIP en GitHub.
"""

import os
import sys
import zipfile
import subprocess
import requests

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_OWNER = "pabloemmanueldeleo"
REPO_NAME = "TapoC225-Baby-Monitor"
TAG_NAME = "v1.0.0"
ZIP_PATH = "TapoC225_BabyMonitor_Windows.zip"

def get_github_token() -> str:
    # 1. Variable de entorno
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    # 2. Archivo .env
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GITHUB_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if token:
                        return token
    # 3. Windows / System Git Credential Manager
    try:
        res = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            text=True,
            capture_output=True,
            timeout=5
        )
        if res.returncode == 0:
            creds = dict(l.split("=", 1) for l in res.stdout.splitlines() if "=" in l)
            pwd = creds.get("password", "")
            if pwd:
                return pwd
    except Exception:
        pass
    return ""

def run_local_tests() -> bool:
    print("\n" + "=" * 60)
    print(" [TESTS] EJECUTANDO PRUEBAS UNITARIAS EN SEGUNDO PLANO (OFFSCREEN)")
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

def build_executable_and_zip(zip_path: str, force_rebuild: bool = True) -> bool:
    print("\n" + "=" * 60)
    print(" [BUILD] COMPILANDO EJECUTABLE Y CREANDO ARCHIVO ZIP ACTUALIZADO")
    print("=" * 60)

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
        
    # 3. Comprimir a ZIP con compresión máxima
    print(f"[*] Comprimiendo '{dist_folder}' en '{zip_path}'...")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(dist_folder):
            for f in files:
                fp = os.path.join(root, f)
                arcname = os.path.relpath(fp, "dist")
                zf.write(fp, arcname)
    
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"[OK] Archivo ZIP ultra-comprimido generado exitosamente: {zip_path} ({size_mb:.1f} MB)")
    return True

def delete_all_github_releases_and_tags(token: str):
    print("\n" + "=" * 60)
    print(" [*] 1. ELIMINANDO TODAS LAS RELEASES Y TAGS DE GITHUB")
    print("=" * 60)
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # 1. Borrar todas las releases
    r = requests.get(f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases", headers=headers)
    if r.status_code == 200:
        releases = r.json()
        for rel in releases:
            rel_id = rel["id"]
            tag = rel.get("tag_name", "unknown")
            print(f"[*] Borrando Release '{tag}' (ID: {rel_id}) en GitHub...")
            requests.delete(f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/{rel_id}", headers=headers)
            
    # 2. Borrar todos los tags remotos via API
    r_tags = requests.get(f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/git/matching-refs/tags", headers=headers)
    if r_tags.status_code == 200:
        refs = r_tags.json()
        for ref in refs:
            ref_name = ref.get("ref", "")
            if ref_name.startswith("refs/tags/"):
                tag_sub = ref_name.replace("refs/tags/", "")
                print(f"[*] Borrando Tag remoto '{tag_sub}' en GitHub...")
                requests.delete(f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/git/refs/tags/{tag_sub}", headers=headers)
    print("[OK] Limpieza de Releases y Tags en GitHub completada.")

def squash_to_single_commit():
    print("\n" + "=" * 60)
    print(" [*] 2. UNIFICANDO TODO EL HISTORIAL EN UN SOLO COMMIT RAIZ")
    print("=" * 60)
    
    # Borrar tags locales
    try:
        tags_out = subprocess.check_output(["git", "tag", "-l"], text=True).strip().split()
        for t in tags_out:
            if t:
                subprocess.run(["git", "tag", "-d", t], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
        
    # Crear rama huerfana limpia
    subprocess.run(["git", "checkout", "--orphan", "clean_main_branch"], check=True)
    subprocess.run(["git", "add", "-A"], check=True)
    subprocess.run(["git", "commit", "-m", "feat: initial release - TapoC225 AI Baby Monitor & Sleep Analytics System"], check=True)
    
    # Reemplazar main
    subprocess.run(["git", "branch", "-D", "main"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "branch", "-m", "main"], check=True)
    
    # Force push main
    print("[*] Subiendo commit unico y limpio a GitHub (force push)...")
    subprocess.run(["git", "push", "origin", "main", "--force"], check=True)
    
    # Crear tag v1.0.0 local y subirlo
    print("[*] Creando y subiendo tag oficial 'v1.0.0'...")
    subprocess.run(["git", "tag", "-a", TAG_NAME, "-m", f"Release {TAG_NAME} - Official Initial Release"], check=True)
    subprocess.run(["git", "push", "origin", TAG_NAME, "--force"], check=True)
    print("[OK] Rama main y tag v1.0.0 sincronizados como nuevo commit inicial.")

def create_fresh_github_release(token: str):
    print("\n" + "=" * 60)
    print(" [*] 3. CREANDO NUEVA RELEASE OFICIAL EN GITHUB")
    print("=" * 60)
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    payload = {
        "tag_name": TAG_NAME,
        "name": f"Release {TAG_NAME} - TapoC225 AI Baby Monitor & Sleep Analytics",
        "body": "### TapoC225 AI Baby Monitor — Official Standalone Windows Release\n\n* **Ejecutable nativo para Windows (64-bit)** listo para usar (no requiere Python).\n* **100% Privado (Edge AI)**: todo el procesamiento corre en tu red local sin suscripciones ni nube.\n* **Incluye**: Deteccion YOLOv8n-seg, filtrado de sabanas y adultos, monitor de audio y panel de sueno pediatrico con Matplotlib.",
        "draft": False,
        "prerelease": False
    }
    
    res = requests.post(f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases", json=payload, headers=headers)
    if res.status_code not in (200, 201):
        print(f"[ERROR] No se pudo crear la release: {res.status_code} - {res.text}")
        return
        
    rel_data = res.json()
    rel_id = rel_data["id"]
    upload_url_template = rel_data["upload_url"]
    print(f"[OK] Release creada exitosamente en GitHub (ID: {rel_id}).")
    
    upload_url = upload_url_template.split("{")[0] + f"?name={os.path.basename(ZIP_PATH)}"
    upload_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/zip"
    }
    
    size_mb = os.path.getsize(ZIP_PATH) / (1024 * 1024)
    print(f"[*] Subiendo binario '{ZIP_PATH}' ({size_mb:.1f} MB) a la nueva Release...")
    with open(ZIP_PATH, "rb") as f:
        up_res = requests.post(upload_url, data=f.read(), headers=upload_headers)
        
    if up_res.status_code in (200, 201):
        print("\n" + "=" * 60)
        print(" [EXITO TOTAL] TODO EL REPOSITORIO QUEDO COMO NUEVO:")
        print(f" -> 1 solo commit inicial en 'main'")
        print(f" -> 1 solo tag limpio: '{TAG_NAME}'")
        print(f" -> 1 sola Release oficial con su binario listo para descargar:")
        print(f"    https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/tag/{TAG_NAME}")
        print("=" * 60)
    else:
        print(f"[ERROR] Error al subir el binario: {up_res.status_code} - {up_res.text}")

def main():
    token = get_github_token()
    if not token:
        print("[ERROR] No se encontro GITHUB_TOKEN en .env")
        return
    
    # 1. Tests
    if not run_local_tests():
        return

    # 2. Build ejecutable & ZIP
    if not build_executable_and_zip(ZIP_PATH, force_rebuild=True):
        return
        
    # 3. Limpieza remota de releases/tags
    delete_all_github_releases_and_tags(token)
    
    # 4. Squash a commit unico limpio
    squash_to_single_commit()
    
    # 5. Crear nueva release y subir binario
    create_fresh_github_release(token)

if __name__ == "__main__":
    main()
