"""MySQL member profiles, portrait validation and AI cache."""
import hashlib, io, json, os, re, subprocess, sys, tempfile, threading, uuid
from datetime import date
from pathlib import Path
import mysql.connector
from flask import Blueprint, jsonify, render_template, request, send_file
from component_status import database_error

MAX_PHOTO = 6 * 1024 * 1024

class MemberStore:
    def __init__(self, connect, base, ensure_db=None):
        self.connect, self.base = connect, Path(base)
        self.ensure_db = ensure_db
        self.cache = self.base / 'data' / 'face_registry.json'
        self.lock = threading.RLock()
        self.profiles = {}
        self.initialized = False
        if self.cache.is_file():
            try:
                self.profiles = {r["key"]:r.get("profile", {}) for r in json.loads(self.cache.read_text(encoding="utf8"))}
            except (ValueError,OSError):
                pass

    def initialize(self):
        with self.lock:
            if not self.initialized:
                if self.ensure_db:
                    self.ensure_db()
                self.ensure()
                self.refresh()
                self.import_legacy()
                self.initialized = True
                return True
            return False

    def ensure(self):
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute('''CREATE TABLE IF NOT EXISTS members (
                id CHAR(32) PRIMARY KEY, recognition_key VARCHAR(255) UNIQUE NOT NULL,
                full_name VARCHAR(150) NOT NULL, birth_date DATE NULL,
                phone VARCHAR(30) NOT NULL DEFAULT '', apartment VARCHAR(80) NOT NULL DEFAULT '',
                portrait MEDIUMBLOB NOT NULL, encoding TEXT NOT NULL,
                photo_hash CHAR(64) UNIQUE NOT NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) DEFAULT CHARSET=utf8mb4''')
            conn.commit()
            cur.close()
        finally:
            conn.close()

    def rows(self, include_encoding=False):
        conn = self.connect()
        try:
            cur = conn.cursor(dictionary=True)
            columns = 'id,recognition_key,full_name,birth_date,phone,apartment,active,created_at,updated_at'
            if include_encoding:
                columns += ',encoding'
            cur.execute('SELECT '+columns+' FROM members ORDER BY created_at,id')
            rows = cur.fetchall()
            cur.close()
            for row in rows:
                row['active'] = bool(row['active'])
                for key in ('birth_date','created_at','updated_at'):
                    if row[key] is not None:
                        row[key] = row[key].isoformat()
                row['photo_url'] = '/api/members/'+row['id']+'/photo'
            return rows
        finally:
            conn.close()

    def refresh(self):
        rows = self.rows(include_encoding=True)
        registry = [{'key':r['recognition_key'], 'encoding':json.loads(r['encoding']),
                     'profile':{k:r[k] for k in ('id','full_name','apartment','active')}}
                    for r in rows if r['active']]
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache.with_suffix('.tmp')
        temporary.write_text(json.dumps(registry), encoding='utf8')
        os.replace(temporary, self.cache)
        self.profiles = {r['recognition_key']:{k:v for k,v in r.items() if k!='encoding'} for r in rows}
        return self.rows()

    def save(self, fields, photo=None, encoding=None, member_id=None, legacy_key=None):
        conn = self.connect()
        try:
            cur = conn.cursor()
            if member_id:
                cur.execute('SELECT id FROM members WHERE id=%s', (member_id,))
                if not cur.fetchone():
                    raise LookupError('Không tìm thấy thành viên.')
                sql = 'UPDATE members SET full_name=%s,birth_date=%s,phone=%s,apartment=%s,active=%s'
                args = [fields[k] for k in ('full_name','birth_date','phone','apartment','active')]
                if photo is not None:
                    sql += ',portrait=%s,encoding=%s,photo_hash=%s'
                    args += [photo, json.dumps(encoding), hashlib.sha256(photo).hexdigest()]
                cur.execute(sql+' WHERE id=%s', tuple(args+[member_id]))
            else:
                member_id = uuid.uuid4().hex
                key = legacy_key or ('person-'+member_id)
                cur.execute('''INSERT INTO members
                    (id,recognition_key,full_name,birth_date,phone,apartment,active,portrait,encoding,photo_hash)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (member_id,key,fields['full_name'],fields['birth_date'],fields['phone'],fields['apartment'],
                     fields['active'],photo,json.dumps(encoding),hashlib.sha256(photo).hexdigest()))
            conn.commit()
            cur.close()
            return member_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def portrait(self, member_id):
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute('SELECT portrait FROM members WHERE id=%s', (member_id,))
            row = cur.fetchone()
            cur.close()
            return bytes(row[0]) if row else None
        finally:
            conn.close()

    def status(self):
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute('SELECT DATABASE(),VERSION()')
            name,version = cur.fetchone()
            counts = {}
            for table in ('members','lich_su_thoat_hiem','camera_photos'):
                cur.execute('SELECT COUNT(*) FROM '+table)
                counts[table] = cur.fetchone()[0]
            cur.close()
            return {'ok':True,'database':name,'engine':version,'tables':counts,
                    'photo_storage':'Ảnh hồ sơ lưu trong bảng members; ảnh camera lưu trong static/captures.'}
        finally:
            conn.close()

    def encode(self, raw):
        if not raw or len(raw)>MAX_PHOTO:
            raise ValueError('Ảnh phải có dung lượng từ 1 byte đến 6 MB.')
        parent = self.base / 'data' / 'enrollment'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            folder = Path(folder)
            (folder/'input').write_bytes(raw)
            try:
                result = subprocess.run([sys.executable,str(self.base/'enrollment.py'),
                    str(folder/'input'),str(folder/'portrait.jpg'),str(folder/'result.json')],
                    capture_output=True, timeout=60,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            except subprocess.TimeoutExpired:
                raise ValueError('Xử lý ảnh quá lâu; hãy chọn ảnh nhỏ hơn, rõ một khuôn mặt.')
            if not (folder/'result.json').exists():
                raise RuntimeError('Không chạy được AI kiểm tra ảnh; kiểm tra thư viện Python.')
            data = json.loads((folder/'result.json').read_text(encoding='utf8'))
            if result.returncode or 'error' in data:
                raise ValueError(data.get('error','Không xử lý được ảnh.'))
            return (folder/'portrait.jpg').read_bytes(), data['encoding']

    def import_legacy(self):
        existing = set(self.profiles)
        for file in sorted((self.base/'dataset').glob('*')):
            if file.suffix.lower() not in ('.jpg','.jpeg','.png'):
                continue
            key = file.stem.replace('_',' ')
            if key in existing:
                continue
            try:
                photo, encoding = self.encode(file.read_bytes())
                self.save({'full_name':key,'birth_date':None,'phone':'','apartment':'','active':True},
                          photo, encoding, legacy_key=key)
            except (ValueError,mysql.connector.IntegrityError) as error:
                print('[MEMBERS] Legacy portrait skipped:',type(error).__name__,flush=True)
        self.refresh()


def validate_fields(data):
    result = {}
    for key,maximum in (('full_name',150),('phone',30),('apartment',80)):
        value = str(data.get(key,'')).strip()
        if len(value)>maximum or any(ord(c)<32 for c in value):
            raise ValueError('Thông tin quá dài hoặc có ký tự không hợp lệ.')
        result[key] = value
    if not result['full_name']:
        raise ValueError('Cần nhập họ tên.')
    birth = str(data.get('birth_date','')).strip()
    result['birth_date'] = date.fromisoformat(birth) if birth else None
    if result['birth_date'] and result['birth_date']>date.today():
        raise ValueError('Ngày sinh không được ở tương lai.')
    active = data.get('active','true')
    if active not in ('true','false',True,False):
        raise ValueError('Trạng thái thành viên không hợp lệ.')
    result['active'] = active in ('true',True)
    return result


def install_members(app, store, changed):
    api = Blueprint('members',__name__)
    # Local dashboard uses same-origin requests. Reject cross-site profile changes.
    @api.before_request
    def protect_changes():
        if request.method in ('POST','PUT'):
            origin = request.headers.get('Origin')
            if origin and origin.rstrip('/')!=request.host_url.rstrip('/'):
                return jsonify(ok=False,message='Chỉ lưu hồ sơ từ trang web của dự án.'),403

    @api.get('/members')
    def page():
        return render_template('members.html')

    @api.get('/api/members')
    def listing():
        try:
            if store.initialize():
                changed()
            return jsonify(ok=True,members=store.rows())
        except mysql.connector.Error as error:
            return jsonify(ok=False, **database_error(error)),503

    @api.get('/api/database/status')
    def database_status():
        try:
            store.initialize()
            return jsonify(store.status())
        except mysql.connector.Error as error:
            return jsonify(ok=False,database='iot_dongdat', **database_error(error)),503

    @api.get('/api/members/<member_id>/photo')
    def photo(member_id):
        if not re.fullmatch('[0-9a-f]{32}',member_id):
            return jsonify(ok=False,message='Mã thành viên không hợp lệ.'),404
        try:
            raw=store.portrait(member_id)
        except mysql.connector.Error as error:
            return jsonify(ok=False, **database_error(error)),503
        if raw is None:
            return jsonify(ok=False,message='Không tìm thấy ảnh.'),404
        return send_file(io.BytesIO(raw),mimetype='image/jpeg',max_age=0)

    @api.post('/api/members')
    @api.put('/api/members/<member_id>')
    def save(member_id=None):
        if member_id and not re.fullmatch('[0-9a-f]{32}',member_id):
            return jsonify(ok=False,message='Mã thành viên không hợp lệ.'),404
        try:
            fields=validate_fields(request.form)
            upload=request.files.get('photo')
            if not member_id and (not upload or not upload.filename):
                raise ValueError('Cần chọn ảnh chân dung JPG hoặc PNG.')
            # Check DB before the expensive face analysis.
            if store.initialize():
                changed()
            store.rows()
            photo=encoding=None
            if upload and upload.filename:
                photo,encoding=store.encode(upload.stream.read(MAX_PHOTO+1))
            with store.lock:
                saved=store.save(fields,photo,encoding,member_id)
                try:
                    store.refresh()
                except (OSError, mysql.connector.Error):
                    return jsonify(ok=True,id=saved,ai_updated=False,
                        message='Hồ sơ đã lưu vào MySQL, nhưng chưa cập nhật AI. Kiểm tra MySQL, quyền ghi thư mục data và khởi động lại web.'),200
                changed()
            return jsonify(ok=True,id=saved,ai_updated=True,message='Đã lưu hồ sơ. AI đang cập nhật danh sách.'),200 if member_id else 201
        except mysql.connector.IntegrityError:
            return jsonify(ok=False,message='Ảnh này đã thuộc một hồ sơ. Hãy sửa hồ sơ đó hoặc dùng ảnh khác.'),409
        except mysql.connector.Error as error:
            return jsonify(ok=False, **database_error(error)),503
        except LookupError as error:
            return jsonify(ok=False,message=str(error)),404
        except (ValueError,TypeError) as error:
            return jsonify(ok=False,message=str(error)),422
        except (OSError,RuntimeError):
            app.logger.exception('Member enrollment failed')
            return jsonify(ok=False,message='Không xử lý được ảnh hoặc ghi dữ liệu; xem log web.'),500

    app.register_blueprint(api)
