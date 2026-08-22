"""
Gestor Completo de Publicación y Releases en GitHub para TapoC225 Baby Monitor.
Limpia versiones obsoletas, asegura que NINGÚN dato sensible ni personal sea distribuido,
y publica la release limpia y estable.
"""
import os
import sys
import shutil
import zipfile
import subprocess
import requests

REPO_OWNER = "pabloemmanueldeleo"
REPO_NAME = "TapoC225-Baby-Monitor"

def get_github_token() -> str:
    token = os.getenv("GITHUB_TOKEN", "").strip() or os.getenv("GH_TOKEN", "").strip()
    if token:
        return token
    try:
        p = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        out, _ = p.communicate('protocol=https\nhost=github.com\n')
        for line in out.splitlines():
            if line.startswith('password='):
                return line.split('=', 1)[1].strip()
    except Exception as e:
        print(f"[WARN] Error obteniendo credenciales de git: {e}")
    return ""

def get_headers(token: str):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

def list_releases(token: str):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases"
    resp = requests.get(url, headers=get_headers(token))
    if resp.status_code == 200:
        return resp.json()
    print(f"[ERROR] No se pudieron listar releases ({resp.status_code}): {resp.text}")
    return []

def delete_all_old_releases(token: str):
    releases = list_releases(token)
    print(f"\n[*] Encontradas {len(releases)} releases existentes.")
    for r in releases:
        rel_id = r.get("id")
        tag_name = r.get("tag_name")
        print(f"[*] Eliminando release ID {rel_id} (Tag: {tag_name})...")
        del_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/{rel_id}"
        del_resp = requests.delete(del_url, headers=get_headers(token))
        if del_resp.status_code == 204:
            print(f"    [OK] Release {tag_name} eliminada.")
        else:
            print(f"    [WARN] No se pudo eliminar release {tag_name}: {del_resp.status_code}")
        
        # Eliminar tag remoto en GitHub si existe
        if tag_name:
            tag_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/git/refs/tags/{tag_name}"
            requests.delete(tag_url, headers=get_headers(token))

def clean_dist_of_sensitive_data():
    """
    Elimina estrictamente cualquier residuo de uso local dentro de dist/
    (fotos de bebé, configuraciones personales, base de datos de telemetría, logs, .env)
    """
    print("\n" + "=" * 60)
    print(" [*] SANITIZANDO DIRECTORIO DIST (LIMPIEZA DE DATOS PRIVADOS)")
    print("=" * 60)
    
    dist_dir = os.path.join("dist", "TapoC225_BabyMonitor")
    if not os.path.exists(dist_dir):
        print(f"[!] No existe {dist_dir}")
        return

    sensitive_paths = [
        os.path.join(dist_dir, "data"),
        os.path.join(dist_dir, "templates"),
        os.path.join(dist_dir, "templates_negatives"),
        os.path.join(dist_dir, "captures"),
        os.path.join(dist_dir, "snapshots"),
        os.path.join(dist_dir, ".env"),
        os.path.join(dist_dir, "config.json"),
        os.path.join(dist_dir, "crash_log.txt"),
    ]

    for p in sensitive_paths:
        if os.path.exists(p):
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
                print(f"[LIMPIO] Carpeta de datos personales eliminada: {p}")
            else:
                try:
                    os.remove(p)
                    print(f"[LIMPIO] Archivo sensible eliminado: {p}")
                except Exception as e:
                    print(f"[WARN] Error eliminando {p}: {e}")

    # Asegurar que .env.example exista en dist
    env_example_src = ".env.example"
    env_example_dst = os.path.join(dist_dir, ".env.example")
    if os.path.exists(env_example_src):
        shutil.copyfile(env_example_src, env_example_dst)
        print(f"[OK] .env.example incluido como plantilla limpia.")

def create_clean_zip_package(zip_path: str) -> bool:
    print("\n" + "=" * 60)
    print(f" [*] CREANDO ARCHIVO ZIP PARA DISTRIBUCIÓN: {zip_path}")
    print("=" * 60)
    
    dist_dir = os.path.join("dist", "TapoC225_BabyMonitor")
    exe_path = os.path.join(dist_dir, "TapoC225_BabyMonitor.exe")
    
    if not os.path.exists(exe_path):
        print(f"[ERROR] No se encuentra el ejecutable en '{exe_path}'.")
        return False

    clean_dist_of_sensitive_data()

    if os.path.exists(zip_path):
        try:
            os.remove(zip_path)
        except Exception:
            pass

    print(f"[*] Comprimiendo paquete limpio...")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(dist_dir):
            for f in files:
                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, dist_dir)
                
                # Excluir cualquier archivo o carpeta de usuario en la raiz de la aplicacion
                parts = rel_p.split(os.sep)
                if parts[0] in ["data", "templates", "templates_negatives", "captures", "snapshots", ".env", "config.json", "crash_log.txt"]:
                    print(f"[EXCLUIDO] Archivo/Carpeta local omitida: {rel_p}")
                    continue

                arcname = os.path.join("TapoC225_BabyMonitor", rel_p)
                zf.write(full_p, arcname)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"[OK] Paquete ZIP generado exitosamente: {zip_path} ({size_mb:.1f} MB)")
    return True

def create_and_upload_release(tag_name: str, zip_path: str, token: str) -> bool:
    print("\n" + "=" * 60)
    print(f" [*] CREANDO Y PUBLICANDO RELEASE '{tag_name}' EN GITHUB")
    print("=" * 60)
    
    # 1. Crear release
    release_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases"
    payload = {
        "tag_name": tag_name,
        "target_commitish": "main",
        "name": f"Tapo C225 AI Baby Monitor {tag_name} — Stable Release",
        "body": """## 👶 Tapo C225 AI Baby Monitor & Sleep Analytics (Windows Standalone)

### ✨ Novedades y Mejoras de Rendimiento en esta Versión:
* **⚡ Interfaz a 60 FPS Fluidos:** Desacople adaptativo del motor de inferencia neuronal en background para eliminar cualquier latencia o congelamiento en los controles.
* **🖼️ Renderizado Zero-Copy en C++/Qt:** Eliminada la sobrecarga de conversión de formatos de color en el hilo principal del canvas interactivo.
* **🛡️ 100% Privado y Edge AI:** Todo el análisis de imagen (YOLOv8n-seg), detección de movimiento y monitor de audio corre íntegramente en tu red local sin depender de la nube.
* **🔒 Cierre Limpio y Control de Instancia Única:** Detección y prevención automática de ejecuciones duplicadas en segundo plano.

---
### 🚀 Instrucciones de Instalación:
1. Descarga y descomprime `TapoC225_BabyMonitor_Windows_x64.zip`.
2. Ejecuta `TapoC225_BabyMonitor.exe`.
3. Configura la IP de tu cámara Tapo C225 y tus credenciales de cuenta de cámara (onvif/rtsp).
4. ¡Listo! Todo corre de forma nativa sin necesidad de tener Python instalado.
""",
        "draft": False,
        "prerelease": False
    }

    create_res = requests.post(release_url, json=payload, headers=get_headers(token))
    if create_res.status_code not in (200, 201):
        print(f"[ERROR] No se pudo crear la release ({create_res.status_code}): {create_res.text}")
        return False

    rel_data = create_res.json()
    release_id = rel_data.get("id")
    upload_url_template = rel_data.get("upload_url")
    print(f"[OK] Release creada con éxito (ID: {release_id}).")

    # 2. Subir asset
    upload_url = upload_url_template.split("{")[0] + f"?name={os.path.basename(zip_path)}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/zip",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    file_size = os.path.getsize(zip_path)
    print(f"[*] Subiendo '{zip_path}' ({file_size / (1024*1024):.1f} MB) a GitHub...")
    with open(zip_path, "rb") as f:
        up_res = requests.post(upload_url, headers=headers, data=f)

    if up_res.status_code in (200, 201):
        print(f"\n[OK] ¡Release {tag_name} subida y publicada con éxito!")
        print(f"     URL: https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/tag/{tag_name}")
        return True
    else:
        print(f"[ERROR] Error subiendo el asset ({up_res.status_code}): {up_res.text}")
        return False

if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else "v1.0.6"
    zip_target = "TapoC225_BabyMonitor_Windows_x64.zip"
    
    token = get_github_token()
    if not token:
        print("[ERROR] No se pudo encontrar un token de GitHub válido en el entorno o git credentials.")
        sys.exit(1)
        
    print(f"[*] Iniciando gestión de release para {tag}...")
    delete_all_old_releases(token)
    
    if not create_clean_zip_package(zip_target):
        print("[ERROR] Falló la creación del paquete zip.")
        sys.exit(1)
        
    success = create_and_upload_release(tag, zip_target, token)
    if not success:
        sys.exit(1)

