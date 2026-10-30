"""Local React API and production file server. Run: .venv/Scripts/python.exe server.py"""

import json
import logging
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import correction_service
from correction_service import correct_text, error_message as model_error_message


DIST = Path(__file__).parent / "frontend" / "dist"
MAX_CHARACTERS = 5000


class Handler(BaseHTTPRequestHandler):
    def json_response(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # CORS headers to enable React client on port 5173 to communicate seamlessly
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Origin")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Origin")
        self.end_headers()

    def do_POST(self):
        if urlsplit(self.path).path != "/api/correct":
            self.json_response(404, {"error": "Unknown endpoint."})
            return
        try:
            # Same-origin browser requests only. Vite forwards the local origin.
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8000", "http://localhost:8000"}:
                self.json_response(403, {"error": "This service accepts local editor requests only."})
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 40000:
                self.json_response(413, {"error": "Please enter up to 5,000 characters."})
                return
            if self.headers.get_content_type() != "application/json":
                self.json_response(415, {"error": "Please submit JSON text."})
                return
            payload = json.loads(self.rfile.read(length))
            text = payload.get("text") if isinstance(payload, dict) else None
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Please enter some English text first.")
            if len(text) > MAX_CHARACTERS:
                raise ValueError("Please enter up to 5,000 characters.")
        except (ValueError, UnicodeDecodeError) as error:
            self.json_response(400, {"error": str(error) if not isinstance(error, json.JSONDecodeError) else "Invalid JSON request."})
            return
        try:
            logging.info('RECEIVED TEXT: %r', text)
            result = correct_text(text)
            logging.info('CORRECT RESULT: %r', result)
            self.json_response(200, result)
        except ValueError as error:
            self.json_response(400, {"error": str(error)})
        except Exception as error:
            logging.exception("Grammar correction failed")
            self.json_response(503, {"error": model_error_message(error)})

    def do_GET(self):
        request_path = unquote(urlsplit(self.path).path)
        if request_path == "/api/health":
            self.json_response(200, {"status": "ok", "engine": "LanguageTool", "model_loaded": correction_service.TOOL is not None})
            return
        if request_path.startswith("/api/"):
            self.json_response(404, {"error": "Unknown endpoint."})
            return
        target = (DIST / (request_path.lstrip("/") or "index.html")).resolve()
        if not target.is_relative_to(DIST.resolve()) or not target.is_file():
            self.json_response(404, {"error": "Frontend not found. Run npm install and npm run build in the frontend folder."})
            return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Grammar Studio: http://127.0.0.1:8000", flush=True)
    print("React development mode: run npm run dev in frontend/", flush=True)
    with ThreadingHTTPServer(("127.0.0.1", 8000), Handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

