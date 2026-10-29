"""SQL persistence for private invoice photo proposals and leased jobs."""
from uuid import uuid4
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

def public(row, matches=None):
    if not row:
        return {
            'id': None, 'state': 'none', 'message': None, 'supplier': None,
            'invoiceNumber': None, 'lines': [], 'canRetry': False,
        }
    proposal = row.get('proposal') or {}
    matches = matches or {}
    lines = []
    for line in proposal.get('lines',[]):
        match=matches.get((line['sku'],line['description']), (None,None))
        lines.append({**line,'productId':match[0],'packageId':match[1]})
    can_retry = bool(
        row['state'] == 'failed'
        and not row['job_terminal']
        and row['job_attempts'] < 3
        and row['image_bytes'] is not None
        and row['image_expires_at'] > row['database_now']
    )
    return {
        'id': str(row['id']), 'state': row['state'], 'message': row['message'],
        'supplier': proposal.get('supplier'), 'invoiceNumber': proposal.get('invoiceNumber'),
        'lines': lines, 'canRetry': can_retry,
    }

class InvoicePhotoRepository:
    PHOTO_COLUMNS = '''p.*,j.attempts AS job_attempts,j.terminal AS job_terminal,
        NOW() AS database_now'''

    def latest(self,c,actor,invoice_id):
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(f'''SELECT {self.PHOTO_COLUMNS} FROM inventory_invoice_photos p
                JOIN inventory_invoice_photo_jobs j ON j.photo_id=p.id
                WHERE p.business_id=%s AND p.store_id=%s AND p.invoice_id=%s
                ORDER BY p.created_at DESC,p.id DESC LIMIT 1''',
                (actor.business_id,actor.store_id,invoice_id))
            return cur.fetchone()

    def photo(self,c,actor,photo_id,invoice_id):
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(f'''SELECT {self.PHOTO_COLUMNS} FROM inventory_invoice_photos p
                JOIN inventory_invoice_photo_jobs j ON j.photo_id=p.id
                WHERE p.business_id=%s AND p.store_id=%s AND p.invoice_id=%s AND p.id=%s''',
                (actor.business_id,actor.store_id,invoice_id,photo_id))
            return cur.fetchone()

    def invoice(self,c,actor,invoice_id,lock=False):
        with c.cursor(row_factory=dict_row) as cur:
            suffix = ' FOR UPDATE' if lock else ''
            cur.execute('''SELECT * FROM inventory_invoice_drafts
                WHERE business_id=%s AND store_id=%s AND id=%s''' + suffix,
                (actor.business_id,actor.store_id,invoice_id))
            return cur.fetchone()

    def replay(self,c,actor,request_id):
        return c.execute('''SELECT fingerprint,photo_id FROM inventory_invoice_photo_requests
            WHERE business_id=%s AND store_id=%s AND actor_user_id=%s AND request_id=%s''',
            (actor.business_id,actor.store_id,actor.user_id,request_id)).fetchone()

    def record_request(self,c,actor,request_id,fingerprint,photo_id):
        c.execute('''INSERT INTO inventory_invoice_photo_requests
            (business_id,store_id,actor_user_id,request_id,fingerprint,photo_id)
            VALUES(%s,%s,%s,%s,%s,%s)''',
            (actor.business_id,actor.store_id,actor.user_id,request_id,fingerprint,photo_id))

    def duplicate(self,c,actor,invoice_id,image_hash):
        return c.execute('''SELECT id FROM inventory_invoice_photos
            WHERE business_id=%s AND store_id=%s AND invoice_id=%s AND image_hash=%s
              AND state IN ('queued','running','ready')
            ORDER BY created_at DESC,id DESC LIMIT 1''',
            (actor.business_id,actor.store_id,invoice_id,image_hash)).fetchone()

    def daily_count(self,c,actor):
        return c.execute('''SELECT count(*) FROM inventory_invoice_photos
            WHERE business_id=%s AND store_id=%s AND created_at>=date_trunc('day',NOW())''',
            (actor.business_id,actor.store_id)).fetchone()[0]

    def enqueue(self,c,actor,invoice,image,image_hash,request_id,fingerprint,model,prior=None):
        photo_id = str(prior[0]) if prior else str(uuid4())
        if prior is None:
            c.execute('''INSERT INTO inventory_invoice_photos(id,business_id,store_id,invoice_id,actor_user_id,invoice_version,image_hash,image_bytes,image_expires_at,model,prompt_version,schema_version)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,NOW()+INTERVAL '24 hours',%s,'invoice-photo-v1','invoice-photo-v1')''',
              (photo_id,actor.business_id,actor.store_id,invoice['id'],actor.user_id,
               invoice['version'],image_hash,image,model))
            c.execute('INSERT INTO inventory_invoice_photo_jobs(photo_id) VALUES(%s)',(photo_id,))
        self.record_request(c,actor,request_id,fingerprint,photo_id)
        return photo_id
    def retry(self,c,row):
        result = c.execute('''UPDATE inventory_invoice_photo_jobs
            SET state='queued',terminal=false,available_at=NOW(),last_error=NULL,updated_at=NOW()
            WHERE photo_id=%s AND attempts<3 AND state='failed' AND EXISTS(
                SELECT 1 FROM inventory_invoice_photos p
                WHERE p.id=photo_id AND p.image_bytes IS NOT NULL AND p.image_expires_at>NOW())
            RETURNING photo_id''', (row['id'],)).fetchone()
        if result:
            c.execute('''UPDATE inventory_invoice_photos
                SET state='queued',message=NULL,updated_at=NOW() WHERE id=%s''', (row['id'],))
        return bool(result)

    def claim(self,c):
        self.purge(c)
        exhausted = c.execute('''UPDATE inventory_invoice_photo_jobs
            SET state='failed',terminal=true,lease_token=NULL,lease_expires_at=NULL,
                last_error='Invoice photo reading failed.',updated_at=NOW()
            WHERE state='running' AND lease_expires_at<NOW() AND attempts>=3
            RETURNING photo_id''').fetchall()
        if exhausted:
            c.execute('''UPDATE inventory_invoice_photos
                SET state='failed',message='Invoice photo reading failed.',image_bytes=NULL,updated_at=NOW()
                WHERE id=ANY(%s::uuid[])''', ([row[0] for row in exhausted],))
        token = str(uuid4())
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute('''SELECT photo_id FROM inventory_invoice_photo_jobs
                WHERE NOT terminal AND attempts<3 AND available_at<=NOW()
                  AND (state='queued' OR (state='running' AND lease_expires_at<NOW()))
                ORDER BY available_at,created_at FOR UPDATE SKIP LOCKED LIMIT 1''')
            row = cur.fetchone()
            if not row:
                return None
            cur.execute('''UPDATE inventory_invoice_photo_jobs
                SET state='running',attempts=attempts+1,lease_token=%s,
                    lease_expires_at=NOW()+INTERVAL '120 seconds',updated_at=NOW()
                WHERE photo_id=%s RETURNING attempts''', (token,row['photo_id']))
            attempt = cur.fetchone()['attempts']
            cur.execute('''UPDATE inventory_invoice_photos
                SET state='running',message=NULL,updated_at=NOW() WHERE id=%s RETURNING *''',
                (row['photo_id'],))
            return cur.fetchone(), token, attempt
    def authorized(self,c,row):
        found=c.execute('''SELECT COALESCE(bm.role,sm.role),COALESCE(bm.state,sm.state),u.state,d.state,d.version
          FROM inventory_invoice_photos p JOIN account_users u ON u.id=p.actor_user_id JOIN inventory_invoice_drafts d ON d.id=p.invoice_id
          JOIN stores s ON s.id=p.store_id AND s.business_id=p.business_id AND s.active AND s.accounts_enabled
          JOIN businesses b ON b.id=p.business_id AND b.active
          LEFT JOIN business_memberships bm ON bm.user_id=u.id AND bm.business_id=p.business_id AND bm.role='owner'
          LEFT JOIN account_store_memberships sm ON sm.user_id=u.id AND sm.store_id=p.store_id
          WHERE p.id=%s AND d.business_id=p.business_id AND d.store_id=p.store_id
            AND (bm.user_id IS NOT NULL OR (sm.role='manager' AND sm.business_id=p.business_id
              AND NOT EXISTS(SELECT 1 FROM account_store_memberships other WHERE other.user_id=u.id AND other.state='active' AND other.store_id<>p.store_id)))
          FOR UPDATE OF d''',(row['id'],)).fetchone()
        return bool(found and found[0] in ('owner','manager') and found[1]=='active' and found[2]=='active' and found[3]=='draft' and found[4]==row['invoice_version'])
    def complete(self,c,pid,token,proposal):
        row = c.execute('''UPDATE inventory_invoice_photo_jobs
            SET state='ready',terminal=true,lease_token=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE photo_id=%s AND state='running' AND lease_token=%s AND lease_expires_at>NOW()
            RETURNING photo_id''', (pid,token)).fetchone()
        if not row:
            return False
        c.execute('''UPDATE inventory_invoice_photos
            SET state='ready',proposal=%s,message=NULL,image_bytes=NULL,updated_at=NOW()
            WHERE id=%s''', (Jsonb(proposal),pid))
        return True

    def fail(self,c,pid,token,attempt,message,retryable=True):
        terminal = not retryable or attempt >= 3
        row = c.execute('''UPDATE inventory_invoice_photo_jobs
            SET state='failed',terminal=%s,last_error=%s,available_at=NOW()+INTERVAL '30 seconds',
                lease_token=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE photo_id=%s AND state='running' AND lease_token=%s RETURNING photo_id''',
            (terminal,message,pid,token)).fetchone()
        if row:
            c.execute('''UPDATE inventory_invoice_photos
                SET state='failed',message=%s,
                    image_bytes=CASE WHEN %s THEN NULL ELSE image_bytes END,updated_at=NOW()
                WHERE id=%s''', (message,terminal,pid))
        return bool(row)

    def purge(self,c):
        expired = c.execute('''UPDATE inventory_invoice_photos SET image_bytes=NULL,
            state=CASE WHEN state IN ('queued','running') THEN 'failed' ELSE state END,
            message=CASE WHEN state IN ('queued','running') THEN 'Invoice photo expired.' ELSE message END,
            updated_at=NOW() WHERE image_bytes IS NOT NULL AND image_expires_at<=NOW()
            RETURNING id''').fetchall()
        if expired:
            c.execute('''UPDATE inventory_invoice_photo_jobs
                SET state='failed',terminal=true,lease_token=NULL,lease_expires_at=NULL,
                    last_error='Invoice photo expired.',updated_at=NOW()
                WHERE photo_id=ANY(%s::uuid[])''', ([row[0] for row in expired],))
        return len(expired)
    def matches(self,c,business_id,proposal):
        result={}
        for line in proposal.get('lines',[]):
            if line['sku']:
                rows = c.execute('''SELECT DISTINCT canonical.id,package.id
                    FROM inventory_product_skus sku
                    JOIN inventory_products source
                      ON source.business_id=sku.business_id AND source.id=sku.product_id
                    JOIN inventory_products canonical
                      ON canonical.business_id=source.business_id
                     AND canonical.id=COALESCE(source.canonical_product_id,source.id)
                    LEFT JOIN inventory_packages alias_package
                      ON alias_package.business_id=sku.business_id AND alias_package.id=sku.package_id
                    LEFT JOIN inventory_packages package
                      ON package.business_id=sku.business_id
                     AND package.id=COALESCE(alias_package.redirect_package_id,sku.package_id)
                     AND package.active
                    WHERE sku.business_id=%s AND sku.sku_key=inventory_key(%s)
                      AND canonical.active AND canonical.canonical_product_id IS NULL
                    LIMIT 2''', (business_id,line['sku'])).fetchall()
            else:
                rows = c.execute('''SELECT id,NULL::uuid FROM inventory_products
                    WHERE business_id=%s AND active AND canonical_product_id IS NULL
                      AND inventory_key(name)=inventory_key(%s) LIMIT 2''',
                    (business_id,line['description'])).fetchall()
            if len(rows)==1:result[(line['sku'],line['description'])]=(str(rows[0][0]),str(rows[0][1]) if rows[0][1] else None)
        return result
