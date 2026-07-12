from pydantic import BaseModel
from typing import Optional


class SettingsResponse(BaseModel):
    company_name:           str = 'DeineZeit'
    app_subtitle:           str = 'Zeiterfassung & Stammdaten'
    color_theme:            str = 'orange'
    # Layout-Redesign: Designvorlage + Whitelabel-Farbanpassung
    design_template:        str = 'standard'  # standard|aurora|bento|business|kontor|nordic|midnight|kontrast
    brand_color:            str = ''          # freie Markenfarbe als Hex (leer = color_theme)
    custom_text_color:      str = ''          # Text-Override als Hex (leer = Vorlagenwert)
    custom_bg_color:        str = ''          # Seitenhintergrund-Override als Hex
    custom_surface_color:   str = ''          # Flächen/Karten-Override als Hex
    logo_url:               str = ''        # Original-Logo (Sidebar)
    logo_header_url:        str = ''        # 600×120 für Berichtskopf
    logo_favicon_url:       str = ''        # 32×32 für Browser-Tab
    sidebar_logo_source:    str = 'logo'    # 'logo' | 'favicon' — was die Sidebar zeigt
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
    # Datenschutz (DSGVO): Aufbewahrungsfrist in Jahren (AT: 7, DE: 10)
    gdpr_retention_years:   str = '7'
    # Speicher / Storage
    storage_backend:        str = 'minio'   # 'minio' | 'webdav'
    webdav_url:             str = ''
    webdav_user:            str = ''
    webdav_root_folder:     str = 'DeineZeit'
    # webdav_password wird NICHT zurückgegeben (Sicherheit)
    # OneDrive / Microsoft Graph
    onedrive_use_graph_creds: str = 'false'   # 'true' = ms_* Felder wiederverwenden
    onedrive_tenant_id:       str = ''
    onedrive_client_id:       str = ''
    onedrive_drive_type:      str = 'personal'  # 'personal' | 'sharepoint'
    onedrive_site_id:         str = ''
    onedrive_root_folder:     str = 'DeineZeit'
    # onedrive_client_secret wird NICHT zurückgegeben (Sicherheit)


class SettingsUpdate(BaseModel):
    company_name:           Optional[str] = None
    app_subtitle:           Optional[str] = None
    color_theme:            Optional[str] = None
    # Layout-Redesign: Designvorlage + Whitelabel-Farbanpassung
    design_template:        Optional[str] = None
    brand_color:            Optional[str] = None
    custom_text_color:      Optional[str] = None
    custom_bg_color:        Optional[str] = None
    custom_surface_color:   Optional[str] = None
    sidebar_logo_source:    Optional[str] = None
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
    # Datenschutz (DSGVO)
    gdpr_retention_years:   Optional[str] = None
    # Speicher / Storage
    storage_backend:        Optional[str] = None
    webdav_url:             Optional[str] = None
    webdav_user:            Optional[str] = None
    webdav_password:        Optional[str] = None
    webdav_root_folder:     Optional[str] = None
    # OneDrive / Microsoft Graph
    onedrive_use_graph_creds: Optional[str] = None
    onedrive_tenant_id:       Optional[str] = None
    onedrive_client_id:       Optional[str] = None
    onedrive_client_secret:   Optional[str] = None
    onedrive_drive_type:      Optional[str] = None
    onedrive_site_id:         Optional[str] = None
    onedrive_root_folder:     Optional[str] = None


class TestEmailRequest(BaseModel):
    to_email: str
