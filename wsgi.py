import os
import secrets
from flask import Flask
from models import db
from dotenv import load_dotenv

load_dotenv()


def _load_secret_key(base_dir):
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key

    instance_dir = os.path.join(base_dir, 'instance')
    secret_path = os.path.join(instance_dir, '.secret_key')
    os.makedirs(instance_dir, exist_ok=True)

    if os.path.exists(secret_path):
        with open(secret_path, 'r', encoding='utf-8') as handle:
            key = handle.read().strip()
            if key:
                return key

    key = secrets.token_hex(32)
    with open(secret_path, 'w', encoding='utf-8') as handle:
        handle.write(key)
    os.chmod(secret_path, 0o600)
    return key


def _env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def create_app():
    base_dir = os.path.dirname(__file__)
    app = Flask(__name__, template_folder='app/templates', static_folder='app/static')

    app.config.update(
        SECRET_KEY=_load_secret_key(base_dir),
        SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///irva.db'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=os.path.join(base_dir, 'app', 'uploads'),
        MAX_CONTENT_LENGTH=50 * 1024 * 1024,  # 50 MB
        MAIL_SERVER=os.environ.get('MAIL_SERVER', 'localhost'),
        MAIL_PORT=int(os.environ.get('MAIL_PORT', 25)),
        MAIL_USE_SSL=_env_bool('MAIL_USE_SSL', False),
        MAIL_USE_TLS=_env_bool('MAIL_USE_TLS', False),
        MAIL_USERNAME=os.environ.get('MAIL_USERNAME') or None,
        MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD') or None,
        MAIL_DEFAULT_SENDER=os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@veau-aveyron.fr'),
        PREFERRED_URL_SCHEME=os.environ.get('PREFERRED_URL_SCHEME', 'https'),
        ADMIN_EMAIL=os.environ.get('ADMIN_EMAIL', 'contact@irva.fr'),
        ADMIN_PASSWORD=os.environ.get('ADMIN_PASSWORD', 'irva2025'),
        IRVA_EMAILS={
            'SA4R':    'contact@irva.fr, animations@sa4r.com, contact@sa4r.com, ericissanchou@orange.fr',
            'Natera':  'contact@irva.fr, bovins.abattoir@groupe-unicor.com, sandrine.lenfant@natera.coop',
            'Sudries': 'contact@irva.fr, elvea.tech.bov@gmail.com',
            'Cadars':  'contact@irva.fr',
            'Autre':   'contact@irva.fr',
        },
    )

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)

    with app.app_context():
        db.create_all()

    # Context processor
    from datetime import datetime
    @app.context_processor
    def inject_globals():
        return {'now': datetime.utcnow()}

    # Jinja filter — utilise parse_multiselect pour gérer les artefacts Forminator
    from app.utils import parse_multiselect as _parse_ms
    @app.template_filter('fromjson')
    def fromjson_filter(s):
        return _parse_ms(s)

    # Blueprints
    from app.views.submit import submit_bp
    from app.views.dashboard import dashboard_bp
    from app.views.export import export_bp

    app.register_blueprint(submit_bp)
    app.register_blueprint(dashboard_bp, url_prefix='/admin')
    app.register_blueprint(export_bp, url_prefix='/export')

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=False)
