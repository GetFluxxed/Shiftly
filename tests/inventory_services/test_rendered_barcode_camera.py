"""Rendered contract tests for the native camera boundary and lifecycle guards."""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
from threading import Thread

import pytest
from playwright.sync_api import expect


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='session')
def barcode_camera_bundle(tmp_path_factory):
    out = tmp_path_factory.mktemp('barcode-camera-render') / 'app.js'
    result = subprocess.run([
        os.environ.get('NATIVE_TEST_NODE', 'node'),
        str(ROOT / 'apps/mobile/tests/rendered/build.mjs'), str(out),
        'tests/rendered/camera-entry.tsx',
    ], cwd=ROOT / 'apps/mobile', capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return out.read_bytes()


@pytest.fixture
def barcode_camera_url(barcode_camera_bundle):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass

        def do_GET(self):
            if self.path == '/app.js':
                self.send_response(200)
                self.send_header('Content-Type', 'text/javascript')
                self.end_headers()
                self.wfile.write(barcode_camera_bundle)
                return
            html = '<meta name="viewport" content="width=device-width"><div id="root"></div><script src="/app.js"></script>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(html.encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def open_camera(page, url):
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(url)
    expect(page.get_by_role('heading', name='Scan a product barcode')).to_be_visible()


def test_permission_check_request_guard_and_manual_fallback(page, barcode_camera_url):
    open_camera(page, barcode_camera_url)
    expect(page.get_by_text('Checking camera access…', exact=True)).to_be_visible()
    page.get_by_role('button', name='Enter code instead').click()
    expect(page.get_by_label('Close callback count')).to_have_text('1')

    page.evaluate("window.__cameraTest.permission({granted:false,canAskAgain:true})")
    expect(page.get_by_text('Allow camera access to scan a product barcode.', exact=True)).to_be_visible()
    page.evaluate("window.__cameraTest.requestMode('pending')")
    allow = page.get_by_role('button', name='Allow camera')
    allow.click()
    allow.click(force=True)
    assert page.evaluate('window.__cameraTest.snapshot().requestCalls') == 1
    page.evaluate("window.__cameraTest.settleRequest({granted:true,canAskAgain:true})")
    expect(page.get_by_label('Barcode camera preview')).to_be_visible()


def test_blocked_permission_settings_error_and_manual_fallback(page, barcode_camera_url):
    open_camera(page, barcode_camera_url)
    page.evaluate("window.__cameraTest.permission({granted:false,canAskAgain:false})")
    expect(page.get_by_text('Camera access is blocked.', exact=False)).to_be_visible()
    page.get_by_role('button', name='Open settings').click()
    assert page.evaluate('window.__cameraTest.snapshot().settingsCalls') == 1
    page.evaluate('window.__cameraTest.settingsReject(true)')
    page.get_by_role('button', name='Open settings').click()
    expect(page.get_by_text('Device settings could not be opened.', exact=False)).to_be_visible()
    page.get_by_role('button', name='Enter code instead').click()
    expect(page.get_by_label('Close callback count')).to_have_text('1')


def test_duplicate_native_frames_emit_exactly_one_scan(page, barcode_camera_url):
    open_camera(page, barcode_camera_url)
    page.evaluate("window.__cameraTest.permission({granted:true,canAskAgain:true})")
    expect(page.get_by_label('Barcode camera preview')).to_be_visible()
    page.evaluate('window.__cameraTest.ready()')
    page.evaluate("window.__cameraTest.scan('0036000291452','ean13'); window.__cameraTest.staleScan('0036000291452','ean13')")
    expect(page.get_by_label('Scan callback count')).to_have_text('1')
    expect(page.get_by_label('Last scan')).to_have_text('{"data":"0036000291452","type":"ean13"}')
    expect(page.get_by_text('Camera paused.', exact=True)).to_be_visible()


def test_background_stale_frame_is_ignored_until_deliberate_resume(page, barcode_camera_url):
    open_camera(page, barcode_camera_url)
    page.evaluate("window.__cameraTest.permission({granted:true,canAskAgain:true})")
    expect(page.get_by_label('Barcode camera preview')).to_be_visible()
    page.evaluate('window.__cameraTest.ready()')
    page.evaluate("window.__cameraTest.appState('background'); window.__cameraTest.staleScan('STALE','code128')")
    expect(page.get_by_label('Scan callback count')).to_have_text('0')
    expect(page.get_by_label('Barcode camera preview')).to_have_count(0)
    expect(page.get_by_text('Camera stopped while Shiftly is in the background.', exact=True)).to_be_visible()
    page.evaluate("window.__cameraTest.appState('active')")
    expect(page.get_by_role('button', name='Resume camera')).to_be_visible()
    expect(page.get_by_label('Barcode camera preview')).to_have_count(0)
    page.get_by_role('button', name='Resume camera').click()
    expect(page.get_by_label('Barcode camera preview')).to_be_visible()
    page.evaluate("window.__cameraTest.ready(); window.__cameraTest.scan('LIVE','code128')")
    expect(page.get_by_label('Scan callback count')).to_have_text('1')


def test_android_blur_stops_preview_and_ignores_same_tick_frame_until_resume(page, barcode_camera_url):
    open_camera(page, barcode_camera_url)
    page.evaluate("window.__cameraTest.permission({granted:true,canAskAgain:true})")
    expect(page.get_by_label('Barcode camera preview')).to_be_visible()
    page.evaluate('window.__cameraTest.ready()')
    page.evaluate("window.__cameraTest.appBlur(); window.__cameraTest.staleScan('STALE','code128')")
    expect(page.get_by_label('Scan callback count')).to_have_text('0')
    expect(page.get_by_label('Barcode camera preview')).to_have_count(0)

    page.evaluate('window.__cameraTest.appFocus()')
    expect(page.get_by_role('button', name='Resume camera')).to_be_visible()
    expect(page.get_by_label('Barcode camera preview')).to_have_count(0)
    page.get_by_role('button', name='Resume camera').click()
    expect(page.get_by_label('Barcode camera preview')).to_be_visible()
    page.evaluate("window.__cameraTest.ready(); window.__cameraTest.scan('LIVE','code128')")
    expect(page.get_by_label('Scan callback count')).to_have_text('1')
    expect(page.get_by_label('Last scan')).to_have_text('{"data":"LIVE","type":"code128"}')


def test_unmounted_scanner_ignores_stale_native_callback(page, barcode_camera_url):
    open_camera(page, barcode_camera_url)
    page.evaluate("window.__cameraTest.permission({granted:true,canAskAgain:true})")
    expect(page.get_by_label('Barcode camera preview')).to_be_visible()
    page.evaluate('window.__cameraTest.ready()')
    page.get_by_role('button', name='Unmount scanner').click()
    page.evaluate("window.__cameraTest.staleScan('AFTER-UNMOUNT','code39')")
    expect(page.get_by_label('Scan callback count')).to_have_text('0')


def test_camera_mount_error_remains_recoverable_with_manual_fallback(page, barcode_camera_url):
    open_camera(page, barcode_camera_url)
    page.evaluate("window.__cameraTest.permission({granted:true,canAskAgain:true})")
    expect(page.get_by_label('Barcode camera preview')).to_be_visible()
    page.evaluate("window.__cameraTest.mountError('Native camera unavailable')")
    expect(page.get_by_text('Native camera unavailable', exact=True)).to_be_visible()
    expect(page.get_by_text('Try opening the camera again, or enter the barcode manually.', exact=True)).to_be_visible()
    page.get_by_role('button', name='Enter code instead').click()
    expect(page.get_by_label('Close callback count')).to_have_text('1')


@pytest.mark.parametrize(('payload', 'kind'), [
    ('085900233161', 'ean13'),
    ('6749118517', 'org.iso.Code39'),
])
def test_native_payload_reaches_lookup_unchanged_once(page, barcode_camera_url, payload, kind):
    open_camera(page, barcode_camera_url)
    page.evaluate("window.__cameraTest.permission({granted:true,canAskAgain:true})")
    expect(page.get_by_label('Barcode camera preview')).to_be_visible()
    page.evaluate('window.__cameraTest.ready()')
    page.evaluate("([data,type]) => { window.__cameraTest.scan(data,type); window.__cameraTest.staleScan(data,type); }", [payload, kind])
    expect(page.get_by_label('Scan callback count')).to_have_text('1')
    assert page.get_by_label('Last scan').text_content() == '{"data":"' + payload + '","type":"' + kind + '"}'


def test_small_label_zoom_is_bounded_and_retains_scan_lifecycle(page, barcode_camera_url):
    open_camera(page, barcode_camera_url)
    page.evaluate("window.__cameraTest.permission({granted:true,canAskAgain:true})")
    expect(page.get_by_label('Barcode camera preview')).to_be_visible()
    page.evaluate('window.__cameraTest.ready()')
    zoom_in = page.get_by_role('button', name='Zoom in', exact=True)
    zoom_out = page.get_by_role('button', name='Zoom out', exact=True)
    expect(zoom_out).to_be_disabled()
    assert 'code93' in page.evaluate('window.__cameraTest.snapshot().barcodeTypes')
    for _ in range(4):
        zoom_in.click()
    expect(zoom_in).to_be_disabled()
    assert page.evaluate('window.__cameraTest.snapshot().zoom') == 0.4
    for _ in range(4):
        zoom_out.click()
    expect(zoom_out).to_be_disabled()
    assert page.evaluate('window.__cameraTest.snapshot().zoom') == 0
    for width in (320, 390, 1024):
        page.set_viewport_size({'width': width, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        box = zoom_in.bounding_box()
        assert box and box['height'] >= 48 and box['width'] >= 48
        if directory := os.environ.get('INVENTORY_SCREENSHOT_DIR'):
            page.screenshot(path=str(Path(directory) / f'barcode-camera-{width}.png'), full_page=True)
    page.evaluate("window.__cameraTest.scan('085900233161','ean13')")
    expect(page.get_by_label('Scan callback count')).to_have_text('1')
    expect(zoom_in).to_have_count(0)
