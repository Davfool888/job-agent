"""Utilidades compartidas: cliente Firestore via Admin SDK o emulador.

Nunca lee secretos del codigo: solo variables de entorno.
Ver database/.env.example
"""
import os
import sys


def get_client():
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        print(
            "ERROR: falta 'firebase-admin'.\n"
            "Instalalo (no toca el backend, es solo para estos scripts):\n"
            "  pip install -r database/requirements.txt",
            file=sys.stderr,
        )
        sys.exit(2)

    emulator = os.getenv("FIRESTORE_EMULATOR_HOST")
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if not firebase_admin._apps:
        if emulator:
            # Emulador: no requiere credenciales reales.
            firebase_admin.initialize_app(
                options={"projectId": os.getenv("FIREBASE_PROJECT_ID", "job-agent-dev")}
            )
        elif key_path and os.path.exists(key_path):
            firebase_admin.initialize_app(
                credentials.Certificate(key_path),
                {"storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET", "")},
            )
        else:
            print(
                "ERROR: define FIRESTORE_EMULATOR_HOST (emulador local) o "
                "GOOGLE_APPLICATION_CREDENTIALS (ruta al JSON de la cuenta "
                "de servicio). Ver database/.env.example",
                file=sys.stderr,
            )
            sys.exit(2)
    return firestore.client()
