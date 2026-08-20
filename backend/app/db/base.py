from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Verbindungspool bewusst gesetzt statt Vorgabewerte zu nehmen.
#
# SQLAlchemy legt ohne Angabe 5 dauerhafte Verbindungen an und lässt 10
# zusätzliche zu — zusammen 15. Das klingt viel, ist es aber nicht: Jede
# gleichzeitig bearbeitete Anfrage belegt eine. Ist der Pool leer, warten
# weitere Anfragen 30 Sekunden auf eine freie Verbindung und laufen dann in
# einen Fehler. Von außen sieht das aus, als hinge die Anwendung.
#
# ``pool_pre_ping`` prüft eine Verbindung vor der Benutzung mit einem
# billigen Signal. Ohne das liefert die erste Anfrage nach einem Neustart der
# Datenbank (oder nach einem Netzunterbruch) einen Fehler, obwohl alles
# wieder läuft — die Verbindung im Pool ist dann nur eine Leiche.
#
# ``pool_recycle`` gibt Verbindungen nach einer Stunde von selbst auf. Manche
# Netzwerke und Datenbank-Einstellungen kappen stille Verbindungen nach einer
# festen Zeit; ohne Recycling merkt man das erst beim nächsten Zugriff.
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=3600,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
