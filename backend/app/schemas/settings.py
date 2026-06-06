from pydantic import BaseModel
from typing import Optional


class SettingsResponse(BaseModel):
    company_name:           str = 'DeineZeit'
    app_subtitle:           str = 'Zeiterfassung & Stammdaten'
    color_theme:            str = 'orange'
    logo_url:               str = ''        # Original-Logo (Sidebar)
    logo_header_url:        str = ''        # 600×120 für Berichtskopf
    logo_favicon_url:       str = ''        # 32×32 für Browser-Tab
    # E-Mail (gemeinsam)
    email_provider:         str = 'smtp'    # 'smtp' oder 'graph'
    smtp_from_name:         str = ''
    smtp_from_email:        str = ''
    # SMTP-Modus
    smtp_host:              str = ''
    smtp_port:              str = '587'
    smtp_user:              str = ''
    smtp_tls:               str = 'true'
    # smtp_password wird NICHT zurückgegeben (Sicherheit)
    # Microsoft Graph-Modus
    ms_tenant_id:           str = ''
    ms_client_id:           str = ''
    # ms_client_secret wird NICHT zurückgegeben (Sicherheit)
    # Backup
    backup_keep_days:       str = '30'
    backup_dir:             str = ''
    backup_schedule_time:   str = '02:00'
    backup_last_at:         str = ''
    backup_history:         str = '[]'
    # Firmenkontakt
    company_contact_id:     str = ''
    company_contact_type:   str = ''


class SettingsUpdate(BaseModel):
    company_name:           Optional[str] = None
    app_subtitle:           Optional[str] = None
    color_theme:            Optional[str] = None
    # E-Mail (gemeinsam)
    email_provider:         Optional[str] = None
    smtp_from_name:         Optional[str] = None
    smtp_from_email:        Optional[str] = None
    # SMTP
    smtp_host:              Optional[str] = None
    smtp_port:              Optional[str] = None
    smtp_user:              Optional[str] = None
    smtp_password:          Optional[str] = None
    smtp_tls:               Optional[str] = None
    # Graph
    ms_tenant_id:           Optional[str] = None
    ms_client_id:           Optional[str] = None
    ms_client_secret:       Optional[str] = None
    # Backup
    backup_keep_days:       Optional[str] = None
    backup_dir:             Optional[str] = None
    backup_schedule_time:   Optional[str] = None
    # Firmenkontakt
    company_contact_id:     Optional[str] = None
    company_contact_type:   Optional[str] = None


class TestEmailRequest(BaseModel):
    to_email: str
