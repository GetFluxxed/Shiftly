from uuid import uuid4
import subprocess
import sys
import time

import reporting
from psycopg.types.json import Jsonb

from database import db_connection
from tests.runtime_services.test_worker_process import wait_for,workers


def test_supervised_worker_fairly_completes_briefing_and_sparse_forecast(runtime_settings,workers):
    forecast_id=str(uuid4())
    with db_connection() as db:
        business=db.execute("INSERT INTO businesses(name) VALUES('Forecast worker') RETURNING id").fetchone()[0]
        store=db.execute("""INSERT INTO stores(name,access_code_hash,business_id)
            VALUES('Forecast store','forecast-worker',%s) RETURNING id""",(business,)).fetchone()[0]
        facts={'daily':[],'ingredients':[]}
        source={'snapshotDate':'2026-10-01','facts':facts,
                'coverage':{'windowDays':28,'productionReports':0,'productionDays':0,
                            'shiftReports':0,'truncated':False},
                'recipes':[],'productionEntries':[],'stockAsOf':[],'shiftReports':[]}
        db.execute('''INSERT INTO store_forecasts
            (id,business_id,store_id,source_fingerprint,prompt_version,model,facts,source_snapshot)
            VALUES(%s,%s,%s,repeat('a',64),'production-forecast-v1','test-model',%s,%s)''',
            (forecast_id,business,store,Jsonb(facts),Jsonb(source)))
        db.execute('INSERT INTO store_forecast_jobs(forecast_id,business_id,store_id) VALUES(%s,%s,%s)',
                   (forecast_id,business,store))
    report_id,_=reporting.queue_report('Crew','closing','Worker fairness.',store)
    process,output=workers(runtime_settings.database_url)
    def completed():
        with db_connection() as db:
            return db.execute('SELECT status FROM briefing_jobs WHERE report_id=%s',(report_id,)).fetchone()==('completed',) and db.execute(
                'SELECT status,analysis FROM store_forecasts WHERE id=%s',(forecast_id,)).fetchone()==('ready',None)
    wait_for(completed)
    process.terminate()
    assert process.wait(timeout=4)==0,output.read_text()


def test_blocked_forecast_respects_shutdown_deadline_and_leaves_recoverable_claim(runtime_settings,child_environment,tmp_path):
    forecast_id=str(uuid4())
    with db_connection() as db:
        business=db.execute("INSERT INTO businesses(name) VALUES('Blocked forecast') RETURNING id").fetchone()[0]
        store=db.execute("""INSERT INTO stores(name,access_code_hash,business_id)
            VALUES('Blocked store','blocked-forecast',%s) RETURNING id""",(business,)).fetchone()[0]
        source={'snapshotDate':'2026-10-01','coverage':{'productionDays':7}}
        db.execute("""INSERT INTO store_forecasts
            (id,business_id,store_id,source_fingerprint,prompt_version,model,facts,source_snapshot)
            VALUES(%s,%s,%s,repeat('b',64),'test-v1','fake','{}',%s)""",
            (forecast_id,business,store,Jsonb(source)))
        db.execute('INSERT INTO store_forecast_jobs(forecast_id,business_id,store_id) VALUES(%s,%s,%s)',
                   (forecast_id,business,store))
    script="""
import time,urllib.request
from config import load_settings
from backend.shiftly.jobs.worker import run_worker

def forbidden(*args,**kwargs):raise AssertionError('Network forbidden')
urllib.request.urlopen=forbidden

def blocked(*args):time.sleep(60)
run_worker(load_settings(load_env=False),provider=forbidden,forecast_provider=blocked,install_signals=True)
"""
    output=tmp_path/'blocked-forecast.log'
    with output.open('w') as handle:
        process=subprocess.Popen([sys.executable,'-c',script],stdout=handle,stderr=subprocess.STDOUT,
            env=child_environment(runtime_settings.database_url,SHUTDOWN_TIMEOUT='0.2'))
        def job():
            with db_connection() as db:
                return db.execute('SELECT state,attempts,terminal FROM store_forecast_jobs WHERE forecast_id=%s',
                                  (forecast_id,)).fetchone()
        try:
            wait_for(lambda:job()==('processing',1,False))
            start=time.monotonic();process.terminate()
            assert process.wait(timeout=3)!=0
            assert time.monotonic()-start<3
            assert 'shutdown deadline exceeded' in output.read_text()
            assert job()==('processing',1,False)
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=3)
