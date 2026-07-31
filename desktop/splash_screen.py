import os
import json
import logging

logger = logging.getLogger(__name__)


class SplashScreen:
    def __init__(self, logo_path=None):
        self._window = None
        self._logo_path = logo_path

    def set_window(self, window):
        self._window = window

    def build_html(self):
        import base64
        logo_html = ''
        if self._logo_path and os.path.exists(self._logo_path):
            try:
                from PIL import Image
                import io
                img = Image.open(self._logo_path)
                img.thumbnail((300, 200), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                b64 = base64.b64encode(buf.getvalue()).decode()
                logo_html = f'<img src="data:image/png;base64,{b64}" alt="CIENTO IMMOBILIER" style="max-width:280px;max-height:180px;object-fit:contain;">'
            except Exception as e:
                logger.warning(f'Could not load splash logo: {e}')

        color_primary = '#0d6efd'
        color_bg = '#1a1a2e'
        color_accent = '#e94560'

        return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>CIENTO IMMOBILIER</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family:'Segoe UI',system-ui,sans-serif;
    background:{color_bg}; color:#fff;
    display:flex; flex-direction:column; align-items:center; justify-content:center;
    height:100vh; overflow:hidden;
    user-select:none;
  }}
  .container {{ text-align:center; padding:40px; }}
  .logo-area {{ margin-bottom:30px; min-height:180px; display:flex; align-items:center; justify-content:center; }}
  h1 {{ font-size:28px; font-weight:300; letter-spacing:2px; margin-bottom:8px; }}
  .subtitle {{ font-size:13px; color:#8899aa; letter-spacing:4px; text-transform:uppercase; margin-bottom:40px; }}
  .progress-container {{ width:360px; }}
  .progress-bar-bg {{ height:4px; background:#2a2a4a; border-radius:2px; overflow:hidden; }}
  .progress-bar-fill {{ height:100%; width:0%; background:linear-gradient(90deg,{color_primary},{color_accent}); border-radius:2px; transition:width 0.3s ease; }}
  .status {{ margin-top:16px; font-size:13px; color:#99aabb; min-height:20px; }}
  .percent {{ font-size:12px; color:#667788; margin-top:6px; }}
  .spinner {{ margin-top:24px; }}
  .spinner::after {{ content:''; display:inline-block; width:20px; height:20px; border:2px solid #2a2a4a; border-top-color:{color_accent}; border-radius:50%; animation:spin 0.8s linear infinite; }}
  @keyframes spin {{ to {{ transform:rotate(360deg); }} }}
  .error {{ color:{color_accent}; font-size:14px; margin-top:20px; }}
  .footer {{ position:absolute; bottom:20px; font-size:11px; color:#445566; }}
</style></head><body>
<div class="container">
  <div class="logo-area">{logo_html}</div>
  <h1>CIENTO IMMOBILIER</h1>
  <div class="subtitle">Enterprise Desktop</div>
  <div class="progress-container">
    <div class="progress-bar-bg"><div class="progress-bar-fill" id="progress"></div></div>
    <div class="status" id="status">Initialisation...</div>
    <div class="percent" id="percent">0%</div>
  </div>
  <div id="error-container" class="error" style="display:none;"></div>
  <div class="spinner" id="spinner"></div>
</div>
<div class="footer">Version 1.0.0 &copy; Ciento Immobilier</div>
<script>
  function cspUpdateProgress(pct, text) {{
    document.getElementById('progress').style.width = pct + '%';
    document.getElementById('status').textContent = text;
    document.getElementById('percent').textContent = pct + '%';
  }}
  function cspShowError(msg) {{
    document.getElementById('error-container').textContent = msg;
    document.getElementById('error-container').style.display = 'block';
    document.getElementById('spinner').style.display = 'none';
  }}
</script>
</body></html>'''

    def update_progress(self, percent, text):
        if self._window:
            try:
                js = f'cspUpdateProgress({percent},{json.dumps(text)})'
                self._window.evaluate_js(js)
            except Exception:
                pass

    def show_error(self, message):
        if self._window:
            try:
                js = f'cspShowError({json.dumps(message)})'
                self._window.evaluate_js(js)
            except Exception:
                pass

    def navigate_to(self, url):
        if self._window:
            try:
                self._window.load_url(url)
            except Exception as e:
                logger.error(f'Failed to navigate to {url}: {e}')
