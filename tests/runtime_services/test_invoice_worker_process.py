"""Separate-process coverage for the durable private invoice-photo worker."""
import subprocess
import sys
import time
from uuid import uuid4

from database import db_connection
from tests.runtime_services.test_worker_process import wait_for


def queued_photo(*, model='queued-invoice-model'):
    photo_id = str(uuid4())
    invoice_id = str(uuid4())
    with db_connection() as connection:
        business_id = connection.execute(
            "INSERT INTO businesses(name) VALUES('Invoice worker') RETURNING id"
        ).fetchone()[0]
        store_id = connection.execute('''INSERT INTO stores
            (name,access_code_hash,business_id,accounts_enabled)
            VALUES('Invoice worker store','invoice-worker',%s,true) RETURNING id''',
            (business_id,)).fetchone()[0]
        user_id = connection.execute('''INSERT INTO account_users
            (username,display_name,password_salt,password_hash)
            VALUES(%s,'Invoice Owner','test','test') RETURNING id''',
            ('invoice-worker-' + photo_id,)).fetchone()[0]
        connection.execute('''INSERT INTO business_memberships
            (user_id,business_id,role) VALUES(%s,%s,'owner')''', (user_id,business_id))
        connection.execute('''INSERT INTO inventory_invoice_drafts
            (id,business_id,store_id,supplier,invoice_number,created_by)
            VALUES(%s,%s,%s,'Worker Supplier','W-1',%s)''',
            (invoice_id,business_id,store_id,user_id))
        connection.execute('''INSERT INTO inventory_invoice_photos
            (id,business_id,store_id,invoice_id,actor_user_id,invoice_version,
             image_hash,image_bytes,image_expires_at,model,prompt_version,schema_version)
            VALUES(%s,%s,%s,%s,%s,1,repeat('a',64),%s,NOW()+INTERVAL '24 hours',
                   %s,'invoice-photo-v1','invoice-photo-v1')''',
            (photo_id,business_id,store_id,invoice_id,user_id,b'private-jpeg',model))
        connection.execute(
            'INSERT INTO inventory_invoice_photo_jobs(photo_id) VALUES(%s)', (photo_id,)
        )
    return photo_id


def photo_state(photo_id):
    with db_connection() as connection:
        return connection.execute('''SELECT p.state,j.state,j.attempts,j.terminal,p.image_bytes,p.model
            FROM inventory_invoice_photos p JOIN inventory_invoice_photo_jobs j ON j.photo_id=p.id
            WHERE p.id=%s''', (photo_id,)).fetchone()


def start_worker(runtime_settings, child_environment, tmp_path, *, blocked=False):
    script = '''
import time, urllib.request
from config import load_settings
from backend.shiftly.jobs.worker import run_worker

def forbidden(*args, **kwargs):
    raise AssertionError("External AI/network is forbidden in this worker test")
urllib.request.urlopen = forbidden

def invoice_provider(image, *, model):
    assert image == b"private-jpeg"
    assert model == "queued-invoice-model"
    if BLOCKED:
        time.sleep(60)
    return {"supplier":"Worker Supplier","invoiceNumber":"W-1","lines":[]}

run_worker(load_settings(load_env=False), provider=forbidden,
           forecast_provider=forbidden, invoice_photo_provider=invoice_provider,
           install_signals=True)
'''.replace('BLOCKED', repr(blocked))
    output = tmp_path / ('blocked-invoice-worker.log' if blocked else 'invoice-worker.log')
    handle = output.open('w+')
    process = subprocess.Popen(
        [sys.executable,'-c',script],
        env=child_environment(
            runtime_settings.database_url,
            OPENAI_MODEL='changed-runtime-model', SHUTDOWN_TIMEOUT='0.2' if blocked else '1',
        ),
        stdout=handle, stderr=subprocess.STDOUT, text=True,
    )
    return process, output, handle


def test_supervised_invoice_worker_completes_without_api_wake_and_stops_gracefully(
    runtime_settings, child_environment, tmp_path,
):
    photo_id = queued_photo()
    process, output, handle = start_worker(
        runtime_settings, child_environment, tmp_path,
    )
    try:
        wait_for(lambda: photo_state(photo_id)[:4] == ('ready','ready',1,True))
        state = photo_state(photo_id)
        assert state[4] is None
        assert state[5] == 'queued-invoice-model'
        process.terminate()
        assert process.wait(timeout=4) == 0, output.read_text()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        handle.close()


def test_blocked_invoice_provider_respects_shutdown_budget_and_leaves_lease_recoverable(
    runtime_settings, child_environment, tmp_path,
):
    photo_id = queued_photo()
    process, output, handle = start_worker(
        runtime_settings, child_environment, tmp_path, blocked=True,
    )
    try:
        wait_for(lambda: photo_state(photo_id)[:4] == ('running','running',1,False))
        started = time.monotonic()
        process.terminate()
        assert process.wait(timeout=3) != 0
        assert time.monotonic() - started < 3
        assert 'shutdown deadline exceeded' in output.read_text()
        assert photo_state(photo_id)[:4] == ('running','running',1,False)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        handle.close()
