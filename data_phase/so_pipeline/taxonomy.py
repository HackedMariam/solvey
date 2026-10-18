"""Exact Solvey taxonomy: 5 categories x 5 subcategories, search specs, relevance profiles."""

from dataclasses import dataclass, field

CATEGORY_TAXONOMY = {
    "Network & VPN": [
        "VPN authentication failure",
        "VPN connection failure",
        "Wi-Fi connectivity issue",
        "DNS/network configuration error",
        "Internet connection problem",
    ],
    "Authentication & Access": [
        "Wrong/expired password",
        "Account locked",
        "MFA/authentication failure",
        "Permission denied",
        "Access to restricted resource",
    ],
    "Email & Communication": [
        "Cannot send email",
        "Cannot receive email",
        "Email authentication failure",
        "Mailbox/storage full",
        "Email client configuration problem",
    ],
    "Software & Applications": [
        "Application won't launch",
        "Application crash",
        "Installation failure",
        "Application configuration error",
        "Software update failure",
    ],
    "System & OS": [
        "Windows/system error",
        "Driver problem",
        "OS update failure",
        "System performance issue",
        "Hardware-related error",
    ],
}

ALL_SUBCATEGORIES = [s for subs in CATEGORY_TAXONOMY.values() for s in subs]
SUBCATEGORY_TO_CATEGORY = {s: c for c, subs in CATEGORY_TAXONOMY.items() for s in subs}

# Subcategory names used by the legacy baseline scripts (scrape_so.py / scrape_so copy.py)
LEGACY_SUBCATEGORY_ALIASES = {
    "DNS configuration error": "DNS/network configuration error",
    "MFA authentication failure": "MFA/authentication failure",
    "Mailbox storage full": "Mailbox/storage full",
}

DIFFICULTY_LEVELS = ("easy", "medium", "hard")
TARGET_PER_CELL = 20


@dataclass(frozen=True)
class SearchSpec:
    """One Stack Exchange API search specification for a subcategory."""

    kind: str                 # 'q' (advanced full-text) or 'tagged' (tag OR search)
    value: str                # query string; or ';'-joined tag list for 'tagged'
    sort: str = "relevance"   # relevance | votes | creation | activity
    bias: str = ""            # '', 'easy' or 'hard' (documentation of intent only)

    def label(self) -> str:
        bias = f"[{self.bias}]" if self.bias else ""
        return f"{self.kind}:{self.value}:{self.sort}{bias}"


# Per-subcategory search plan. Order matters: cheaper/broader specs first.
# Tags are validated at runtime via /tags/{tags}/info; unknown tags are dropped and logged.
SUBCATEGORY_SPECS = {
    "VPN authentication failure": [
        SearchSpec("q", "vpn authentication failure", "relevance"),
        SearchSpec("q", "vpn authentication failed", "relevance"),
        SearchSpec("tagged", "vpn;authentication", "votes"),
        SearchSpec("tagged", "openvpn;authentication", "creation"),
        SearchSpec("q", "vpn certificate authentication error", "relevance", bias="hard"),
        SearchSpec("tagged", "vpn;azure-vpn", "creation"),
        SearchSpec("q", "vpn login rejected credentials", "relevance"),
        SearchSpec("tagged", "vpn;ipsec", "votes"),
    ],
    "VPN connection failure": [
        SearchSpec("q", "vpn connection failure", "relevance"),
        SearchSpec("q", "vpn fails to connect", "relevance"),
        SearchSpec("tagged", "vpn;connection-error", "votes"),
        SearchSpec("tagged", "openvpn", "votes"),
        SearchSpec("tagged", "wireguard", "creation"),
        SearchSpec("q", "vpn disconnects intermittently", "relevance", bias="hard"),
        SearchSpec("tagged", "vpn;cisco-vpn", "creation"),
        SearchSpec("q", "cannot establish vpn tunnel", "relevance"),
    ],
    "Wi-Fi connectivity issue": [
        SearchSpec("q", "wifi connectivity issue", "relevance"),
        SearchSpec("q", "cannot connect to wifi", "relevance"),
        SearchSpec("tagged", "wifi;connection", "votes"),
        SearchSpec("tagged", "wireless-networking", "votes"),
        SearchSpec("tagged", "wifi", "creation"),
        SearchSpec("q", "wifi keeps dropping intermittently", "relevance", bias="hard"),
        SearchSpec("tagged", "wifi;networking", "creation"),
        SearchSpec("q", "connected to wifi no internet access", "relevance"),
    ],
    "DNS/network configuration error": [
        SearchSpec("q", "dns configuration error", "relevance"),
        SearchSpec("q", "dns resolution failure", "relevance"),
        SearchSpec("tagged", "dns;configuration", "votes"),
        SearchSpec("tagged", "dns", "votes"),
        SearchSpec("tagged", "nameserver", "creation"),
        SearchSpec("q", "dns intermittent resolution failure firewall", "relevance", bias="hard"),
        SearchSpec("tagged", "dns;networking", "creation"),
        SearchSpec("q", "dns server not responding configuration", "relevance"),
    ],
    "Internet connection problem": [
        SearchSpec("q", "internet connection problem", "relevance"),
        SearchSpec("q", "no internet access", "relevance"),
        SearchSpec("tagged", "internet;connection", "votes"),
        SearchSpec("tagged", "internet", "votes"),
        SearchSpec("tagged", "connectivity", "creation"),
        SearchSpec("q", "internet drops intermittently router", "relevance", bias="hard"),
        SearchSpec("tagged", "proxy;internet", "creation"),
        SearchSpec("q", "limited connectivity no internet", "relevance"),
    ],
    "Wrong/expired password": [
        SearchSpec("q", "expired password", "relevance"),
        SearchSpec("q", "wrong password error login", "relevance"),
        SearchSpec("tagged", "passwords", "votes"),
        SearchSpec("tagged", "active-directory;passwords", "votes"),
        SearchSpec("q", "password expired cannot login", "relevance"),
        SearchSpec("tagged", "passwords;authentication", "creation"),
        SearchSpec("q", "incorrect password after reset", "relevance"),
        SearchSpec("tagged", "password-policy", "creation"),
    ],
    "Account locked": [
        SearchSpec("q", "account locked", "relevance"),
        SearchSpec("q", "account lockout", "relevance"),
        SearchSpec("tagged", "account-lockout", "votes"),
        SearchSpec("tagged", "active-directory;account-lockout", "creation"),
        SearchSpec("q", "account locked out after failed logins", "relevance"),
        SearchSpec("tagged", "active-directory;login", "votes"),
        SearchSpec("q", "user account locked unlock", "relevance"),
        SearchSpec("tagged", "account-lockout;passwords", "creation"),
    ],
    "MFA/authentication failure": [
        SearchSpec("q", "mfa authentication failure", "relevance"),
        SearchSpec("q", "two factor authentication not working", "relevance"),
        SearchSpec("tagged", "two-factor-authentication", "votes"),
        SearchSpec("q", "mfa verification code not received", "relevance"),
        SearchSpec("tagged", "two-factor-authentication;authentication", "creation"),
        SearchSpec("q", "mfa push notification fails conditional access", "relevance", bias="hard"),
        SearchSpec("q", "authenticator app code rejected", "relevance"),
        SearchSpec("tagged", "two-factor-authentication;active-directory", "votes"),
    ],
    "Permission denied": [
        SearchSpec("q", "permission denied", "relevance"),
        SearchSpec("q", "access denied error", "relevance"),
        SearchSpec("tagged", "permissions", "votes"),
        SearchSpec("tagged", "authorization;permissions", "creation"),
        SearchSpec("q", "permission denied after group policy change", "relevance", bias="hard"),
        SearchSpec("tagged", "permissions;windows", "votes"),
        SearchSpec("q", "operation not permitted error", "relevance"),
        SearchSpec("tagged", "authorization", "creation"),
    ],
    "Access to restricted resource": [
        SearchSpec("q", "access restricted resource", "relevance"),
        SearchSpec("q", "access denied restricted folder", "relevance"),
        SearchSpec("tagged", "http-status-code-403", "votes"),
        SearchSpec("tagged", "authorization;permissions", "votes"),
        SearchSpec("q", "cannot access restricted network share", "relevance"),
        SearchSpec("tagged", "active-directory;permissions", "creation"),
        SearchSpec("q", "forbidden access restricted area", "relevance"),
        SearchSpec("tagged", "http-status-code-403;authorization", "creation"),
    ],
    "Cannot send email": [
        SearchSpec("q", "cannot send email", "relevance"),
        SearchSpec("q", "email sending failed", "relevance"),
        SearchSpec("tagged", "smtp", "votes"),
        SearchSpec("tagged", "email;smtp", "creation"),
        SearchSpec("q", "smtp send failure authentication", "relevance"),
        SearchSpec("tagged", "sendmail", "creation"),
        SearchSpec("q", "outbound email rejected cannot send", "relevance"),
        SearchSpec("tagged", "email;smtp-auth", "votes"),
    ],
    "Cannot receive email": [
        SearchSpec("q", "cannot receive email", "relevance"),
        SearchSpec("q", "not receiving emails", "relevance"),
        SearchSpec("tagged", "imap", "votes"),
        SearchSpec("tagged", "exchange-server", "creation"),
        SearchSpec("tagged", "pop3", "creation"),
        SearchSpec("q", "emails not arriving inbox", "relevance"),
        SearchSpec("q", "incoming mail stopped working", "relevance"),
        SearchSpec("tagged", "email;imap", "votes"),
    ],
    "Email authentication failure": [
        SearchSpec("q", "email authentication failure", "relevance"),
        SearchSpec("q", "smtp authentication failed", "relevance"),
        SearchSpec("tagged", "smtp", "creation"),
        SearchSpec("tagged", "spf", "votes"),
        SearchSpec("tagged", "dkim", "votes"),
        SearchSpec("tagged", "dmarc", "creation"),
        SearchSpec("q", "email rejected spf dkim verification", "relevance", bias="hard"),
        SearchSpec("q", "smtp auth rejected credentials mail server", "relevance"),
    ],
    "Mailbox/storage full": [
        SearchSpec("q", "mailbox full", "relevance"),
        SearchSpec("q", "mailbox quota exceeded", "relevance"),
        SearchSpec("tagged", "exchange-server", "votes"),
        SearchSpec("q", "mailbox storage full cannot send", "relevance"),
        SearchSpec("tagged", "email;quota", "creation"),
        SearchSpec("q", "quota exceeded mail account", "relevance"),
        SearchSpec("tagged", "exchange-server;email", "creation"),
        SearchSpec("q", "mailbox size limit reached", "relevance"),
    ],
    "Email client configuration problem": [
        SearchSpec("q", "email client configuration", "relevance"),
        SearchSpec("q", "configure email client settings", "relevance"),
        SearchSpec("tagged", "outlook", "votes"),
        SearchSpec("tagged", "thunderbird", "creation"),
        SearchSpec("tagged", "imap;outlook", "creation"),
        SearchSpec("q", "email client configuration error settings", "relevance"),
        SearchSpec("tagged", "outlook;smtp", "votes"),
        SearchSpec("q", "mail client setup wrong port server", "relevance"),
    ],
    "Application won't launch": [
        SearchSpec("q", "application won't launch", "relevance"),
        SearchSpec("q", "application fails to start", "relevance"),
        SearchSpec("q", "app does not open error", "relevance"),
        SearchSpec("q", "program will not start error", sort="votes"),
        SearchSpec("q", "application not launching after install", "relevance"),
        SearchSpec("q", "double click program does nothing", sort="votes"),
        SearchSpec("q", "application startup fails missing dependency", "relevance", bias="hard"),
        SearchSpec("tagged", "exe;windows", "creation"),
    ],
    "Application crash": [
        SearchSpec("q", "application crash", "relevance"),
        SearchSpec("q", "application stopped working", "relevance"),
        SearchSpec("tagged", "crash", "votes"),
        SearchSpec("tagged", "crash-dump", "creation"),
        SearchSpec("q", "app crashes stack trace exception", "relevance", bias="hard"),
        SearchSpec("q", "application closes unexpectedly windows", sort="votes"),
        SearchSpec("tagged", "crash;windows", "creation"),
        SearchSpec("q", "faulting application module crash", "relevance"),
    ],
    "Installation failure": [
        SearchSpec("q", "installation failure", "relevance"),
        SearchSpec("q", "failed to install error", "relevance"),
        SearchSpec("tagged", "installer", "votes"),
        SearchSpec("tagged", "msi", "creation"),
        SearchSpec("tagged", "installation", "votes"),
        SearchSpec("q", "installer error code rollback", "relevance", bias="hard"),
        SearchSpec("q", "setup failed installation aborted", "relevance"),
        SearchSpec("tagged", "setup;windows", "creation"),
    ],
    "Application configuration error": [
        SearchSpec("q", "application configuration error", "relevance"),
        SearchSpec("q", "invalid configuration file application", "relevance"),
        SearchSpec("tagged", "configuration", "votes"),
        SearchSpec("q", "app misconfigured settings error", "relevance"),
        SearchSpec("tagged", "configuration;windows", "creation"),
        SearchSpec("q", "configuration file syntax error prevents start", "relevance", bias="hard"),
        SearchSpec("q", "wrong configuration settings application fails", "relevance"),
        SearchSpec("tagged", "config", "creation"),
    ],
    "Software update failure": [
        SearchSpec("q", "software update failure", "relevance"),
        SearchSpec("q", "update failed to install", "relevance"),
        SearchSpec("q", "application update installation error", "relevance"),
        SearchSpec("q", "software update stuck failed", sort="votes"),
        SearchSpec("q", "auto update fails error code", "relevance"),
        SearchSpec("tagged", "updates", "creation"),
        SearchSpec("q", "update rollback failed software", "relevance", bias="hard"),
        SearchSpec("tagged", "upgrade;windows", "creation"),
    ],
    "Windows/system error": [
        SearchSpec("q", "windows system error", "relevance"),
        SearchSpec("q", "windows error code", "relevance"),
        SearchSpec("tagged", "windows", "votes"),
        SearchSpec("tagged", "bsod", "votes"),
        SearchSpec("tagged", "error-code", "creation"),
        SearchSpec("q", "windows crash dump bluescreen", "relevance", bias="hard"),
        SearchSpec("tagged", "windows-10;error", "creation"),
        SearchSpec("q", "system error dialog windows", "relevance"),
    ],
    "Driver problem": [
        SearchSpec("q", "driver problem", "relevance"),
        SearchSpec("q", "driver error windows", "relevance"),
        SearchSpec("tagged", "drivers", "votes"),
        SearchSpec("tagged", "device-driver", "creation"),
        SearchSpec("q", "driver failed to load error", "relevance"),
        SearchSpec("tagged", "drivers;windows", "votes"),
        SearchSpec("q", "driver conflict device manager error", "relevance", bias="hard"),
        SearchSpec("tagged", "printer-driver", "creation"),
    ],
    "OS update failure": [
        SearchSpec("q", "os update failure", "relevance"),
        SearchSpec("q", "windows update failed", "relevance"),
        SearchSpec("tagged", "windows-update", "votes"),
        SearchSpec("tagged", "windows-update;windows-10", "creation"),
        SearchSpec("q", "feature update failed error code", "relevance"),
        SearchSpec("q", "windows update stuck downloading", sort="votes"),
        SearchSpec("tagged", "windows-update;windows-11", "votes"),
        SearchSpec("q", "os upgrade failure rollback", "relevance", bias="hard"),
    ],
    "System performance issue": [
        SearchSpec("q", "system performance issue", "relevance"),
        SearchSpec("q", "computer slow performance", "relevance"),
        SearchSpec("tagged", "performance", "votes"),
        SearchSpec("tagged", "performance;windows", "creation"),
        SearchSpec("q", "high cpu usage slow system", "relevance"),
        SearchSpec("q", "system freeze intermittent performance", "relevance", bias="hard"),
        SearchSpec("tagged", "cpu-usage", "votes"),
        SearchSpec("q", "memory usage high system slow", "relevance"),
    ],
    "Hardware-related error": [
        SearchSpec("q", "hardware error", "relevance"),
        SearchSpec("q", "hardware failure device", "relevance"),
        SearchSpec("tagged", "hardware", "votes"),
        SearchSpec("tagged", "disk", "creation"),
        SearchSpec("q", "hardware device error code", "relevance"),
        SearchSpec("tagged", "hardware;windows", "votes"),
        SearchSpec("q", "hardware failure bluescreen disk error", "relevance", bias="hard"),
        SearchSpec("tagged", "motherboard", "creation"),
    ],
}

# Semantic relevance profiles: used to validate that a returned question really
# belongs to the subcategory it was collected under.
#   tags  -> strong signal (any overlap counts as relevant)
#   strong-> phrases/words that essentially confirm the subcategory (title or body)
#   weak  -> supporting words (need several)
RELEVANCE_PROFILES = {
    "VPN authentication failure": {
        "tags": ["vpn", "openvpn", "ipsec", "wireguard", "cisco-vpn", "azure-vpn",
                 "anyconnect", "pulse-secure", "forticlient", "vpn-client", "ras"],
        "strong": ["vpn auth", "vpn authentication", "authentication failed", "auth failed",
                   "certificate authentication", "aad token", "mfa"],
        "weak": ["vpn", "authentication", "certificate", "credential", "login", "token"],
    },
    "VPN connection failure": {
        "tags": ["vpn", "openvpn", "wireguard", "cisco-vpn", "ipsec", "anyconnect",
                 "azure-vpn", "vpn-client", "pptp", "l2tp"],
        "strong": ["vpn connect", "vpn connection", "connect to vpn", "vpn tunnel",
                   "vpn disconnect", "tunnel establishment"],
        "weak": ["vpn", "connect", "tunnel", "handshake", "disconnect", "remote access"],
    },
    "Wi-Fi connectivity issue": {
        "tags": ["wifi", "wireless-networking", "wlan", "802.11", "wi-fi"],
        "strong": ["wifi", "wi-fi", "wireless", "wlan"],
        "weak": ["connect", "signal", "ssid", "router", "network", "internet", "dropping"],
    },
    "DNS/network configuration error": {
        "tags": ["dns", "nameserver", "host", "networking", "resolv", "dhcp"],
        "strong": ["dns", "name resolution", "nameserver", "name server", "resolver",
                   "nslookup", "dig ", "hosts file"],
        "weak": ["resolve", "resolution", "lookup", "domain", "network", "configuration", "ip"],
    },
    "Internet connection problem": {
        "tags": ["internet", "connectivity", "proxy", "networking", "connection"],
        "strong": ["internet connection", "no internet", "internet access", "cannot access internet",
                   "online", "connection to the internet"],
        "weak": ["internet", "connection", "network", "browse", "proxy", "router", "ethernet"],
    },
    "Wrong/expired password": {
        "tags": ["passwords", "password-policy", "active-directory", "authentication", "login"],
        "strong": ["password expired", "expired password", "wrong password", "incorrect password",
                   "password is wrong", "forgot password", "password reset"],
        "weak": ["password", "login", "sign in", "credential", "authentication", "error"],
    },
    "Account locked": {
        "tags": ["account-lockout", "active-directory", "passwords", "login", "authentication"],
        "strong": ["account locked", "locked out", "lockout", "account is locked",
                   "locked account", "too many failed"],
        "weak": ["account", "locked", "unlock", "login", "failed attempts", "ad"],
    },
    "MFA/authentication failure": {
        "tags": ["two-factor-authentication", "mfa", "authentication", "oauth", "active-directory"],
        "strong": ["mfa", "multi-factor", "multi factor", "two-factor", "two factor",
                   "2fa", "authenticator", "verification code", "otp"],
        "weak": ["authentication", "code", "factor", "push", "token", "verification", "approve"],
    },
    "Permission denied": {
        "tags": ["permissions", "authorization", "access-denied", "chmod", "windows-security"],
        "strong": ["permission denied", "access denied", "not permitted", "eacces",
                   "unauthorized", "access violation"],
        "weak": ["permission", "access", "rights", "policy", "group policy", "folder", "file"],
    },
    "Access to restricted resource": {
        "tags": ["http-status-code-403", "authorization", "permissions", "active-directory",
                 "share", "ntfs"],
        "strong": ["restricted", "403", "forbidden", "not authorized", "cannot access",
                   "access denied", "no access"],
        "weak": ["resource", "share", "folder", "site", "network", "permission", "access"],
    },
    "Cannot send email": {
        "tags": ["email", "smtp", "sendmail", "outlook", "exchange-server", "postfix", "mailgun"],
        "strong": ["cannot send", "can't send", "unable to send", "send email", "sending failed",
                   "failed to send", "outbound mail", "send mail"],
        "weak": ["email", "mail", "smtp", "send", "outlook", "message", "recipient"],
    },
    "Cannot receive email": {
        "tags": ["email", "imap", "pop3", "exchange-server", "postfix", "dovecot", "outlook"],
        "strong": ["cannot receive", "can't receive", "not receiving", "unable to receive",
                   "not getting email", "inbox", "incoming mail", "emails not"],
        "weak": ["email", "mail", "receive", "inbox", "imap", "pop3", "arrive"],
    },
    "Email authentication failure": {
        "tags": ["smtp", "spf", "dkim", "dmarc", "email", "exchange-server", "postfix"],
        "strong": ["smtp auth", "authentication failed", "spf", "dkim", "dmarc",
                   "535", "550", "auth rejected", "smtp error"],
        "weak": ["email", "mail", "authentication", "smtp", "server", "rejected", "relay"],
    },
    "Mailbox/storage full": {
        "tags": ["exchange-server", "email", "imap", "quota", "outlook", "office365"],
        "strong": ["mailbox full", "quota exceeded", "mailbox quota", "storage full",
                   "quota", "mailbox size", "insufficient storage", "over quota"],
        "weak": ["mailbox", "email", "mail", "quota", "storage", "full", "limit"],
    },
    "Email client configuration problem": {
        "tags": ["outlook", "thunderbird", "imap", "pop3", "email", "exchange-server", "eudora"],
        "strong": ["email client", "mail client", "outlook", "thunderbird", "configure",
                   "configuration", "incoming server", "outgoing server", "port"],
        "weak": ["email", "mail", "settings", "account", "server", "smtp", "imap", "setup"],
    },
    "Application won't launch": {
        "tags": ["exe", "windows", "shortcut", "visual-studio", "java", "python"],
        "strong": ["won't launch", "wont launch", "will not launch", "fails to start",
                   "does not open", "not opening", "won't start", "won't open",
                   "cannot start", "won't run", "does not start"],
        "weak": ["launch", "start", "open", "application", "program", "app", "run", "click"],
    },
    "Application crash": {
        "tags": ["crash", "crash-dump", "exception", "segfault", "minidump", "windows"],
        "strong": ["crash", "stopped working", "stopped responding", "has stopped",
                   "faulting", "segfault", "segmentation fault", "aborted", "closes unexpectedly"],
        "weak": ["application", "app", "program", "error", "dump", "exception", "windows"],
    },
    "Installation failure": {
        "tags": ["installer", "installation", "msi", "setup", "installshield", "winget", "chocolatey"],
        "strong": ["installation failed", "failed to install", "install failed", "setup failed",
                   "installer error", "installation error", "rollback", "cannot install",
                   "installation aborted", "msi error"],
        "weak": ["install", "setup", "installer", "msi", "package", "uninstall", "upgrade"],
    },
    "Application configuration error": {
        "tags": ["configuration", "config", "app-config", "settings"],
        "strong": ["configuration error", "configuration file", "config file", "invalid configuration",
                   "misconfigured", "configuration problem", "bad configuration", "config.json",
                   "appsettings", "wrong configuration"],
        "weak": ["configuration", "config", "settings", "application", "app", "file", "error"],
    },
    "Software update failure": {
        "tags": ["updates", "upgrade", "windows", "chocolatey", "npm", "apt", "scoop"],
        "strong": ["update failed", "failed to update", "update failure", "software update",
                   "auto-update", "auto update", "update error", "cannot update",
                   "update stuck", "update rollback"],
        "weak": ["update", "upgrade", "version", "software", "install", "download", "patch"],
    },
    "Windows/system error": {
        "tags": ["windows", "windows-10", "windows-11", "bsod", "error-code", "event-viewer", "windows-7"],
        "strong": ["windows error", "system error", "error code", " bluescreen", "blue screen",
                   "bsod", "event viewer", "system failure", "stop code", "0x"],
        "weak": ["windows", "system", "error", "boot", "crash", "dialog", "event"],
    },
    "Driver problem": {
        "tags": ["drivers", "device-driver", "windows-drivers", "printer-driver", "driver"],
        "strong": ["driver", "device manager", "driver error", "driver failed", "driver problem",
                   "driver conflict", "code 43", "code 10", "driver installation"],
        "weak": ["device", "hardware", "windows", "install", "error", "driver", "usb"],
    },
    "OS update failure": {
        "tags": ["windows-update", "windows-10", "windows-11", "upgrade", "wsus"],
        "strong": ["windows update", "os update", "update failed", "feature update",
                   "windows upgrade", "update error", "0x", "servicing", "wufx"],
        "weak": ["update", "upgrade", "windows", "install", "restart", "version", "error"],
    },
    "System performance issue": {
        "tags": ["performance", "cpu-usage", "memory-leak", "task-manager", "windows", "lag"],
        "strong": ["performance", "slow", "high cpu", "high memory", "freezes", "freezing",
                   "unresponsive", "takes forever", "sluggish", "ram usage"],
        "weak": ["system", "computer", "cpu", "memory", "disk", "process", "usage", "slow"],
    },
    "Hardware-related error": {
        "tags": ["hardware", "disk", "motherboard", "ssd", "hard-drive", "ram", "bios", "cpu"],
        "strong": ["hardware", "disk error", "hard drive", "bios", "motherboard", "ssd failure",
                   "smart", "no boot device", "overheating", "beep code"],
        "weak": ["device", "hardware", "drive", "error", "failure", "computer", "boot", "fan"],
    },
}


# Difficulty-targeted extra search plans used to fill cells left empty by the
# generic specs. Each entry is (spec, difficulty_bias): `easy` bias = short,
# how-to / first-time-user phrasing; `hard` bias = logs, errors, multi-component.
GAP_FILL_SPECS = {
    "VPN authentication failure": [
        (SearchSpec("q", "vpn password forgotten", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "how to setup vpn login", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "vpn two factor authentication prompt", "relevance", bias="easy"), "easy"),
        (SearchSpec("tagged", "vpn;mfa", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "vpn certificate chain validation error logs", "relevance", bias="hard"), "hard"),
    ],
    "Wi-Fi connectivity issue": [
        (SearchSpec("q", "cannot connect to wifi password", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "wifi not showing network simple fix", "votes", bias="easy"), "easy"),
        (SearchSpec("tagged", "wifi;password", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "wifi authentication error event log wireshark", "relevance", bias="hard"), "hard"),
    ],
    "DNS/network configuration error": [
        (SearchSpec("q", "how to fix dns settings", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "dns not resolving simple flush", "votes", bias="easy"), "easy"),
        (SearchSpec("tagged", "dns;windows", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "how to change dns server settings", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "dns server not responding restart router", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "wrong dns settings no internet simple", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "find dns address where to change", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "dns intermittent failure tcpdump packet capture", "relevance", bias="hard"), "hard"),
    ],
    "MFA/authentication failure": [
        (SearchSpec("q", "authenticator app code not working", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "lost phone mfa reset simple", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "mfa push notification fails conditional access logs", "relevance", bias="hard"), "hard"),
        (SearchSpec("q", "two factor authentication intermittent azure ad debug", "relevance", bias="hard"), "hard"),
        (SearchSpec("tagged", "two-factor-authentication;azure-active-directory", "votes", bias="hard"), "hard"),
    ],
    "Email authentication failure": [
        (SearchSpec("q", "email password rejected simple fix", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "cannot send email authentication turn on access", "votes", bias="easy"), "easy"),
        (SearchSpec("tagged", "smtp;password", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "spf dkim dmarc alignment failure logs mail server", "relevance", bias="hard"), "hard"),
    ],
    "Application configuration error": [
        (SearchSpec("q", "how to edit config file application", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "wrong settings application simple fix", "votes", bias="easy"), "easy"),
        (SearchSpec("tagged", "configuration;json", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "config validation error stack trace dependency conflict", "relevance", bias="hard"), "hard"),
    ],
    "Software update failure": [
        (SearchSpec("q", "how to retry software update", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "update failed simple reinstall fix", "votes", bias="easy"), "easy"),
        (SearchSpec("tagged", "updates;windows", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "update rollback failed dependency conflict logs", "relevance", bias="hard"), "hard"),
    ],
    "OS update failure": [
        (SearchSpec("q", "windows update failed simple fix restart", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "how to rerun windows update", "votes", bias="easy"), "easy"),
        (SearchSpec("tagged", "windows-update;fix", "votes", bias="easy"), "easy"),
        (SearchSpec("q", "windows update error code logs dism sfc", "relevance", bias="hard"), "hard"),
    ],
}


def gap_fill_specs_for(subcategory, difficulty=None):
    """Extra (spec, difficulty) pairs for a subcategory, optionally filtered by difficulty."""
    pairs = list(GAP_FILL_SPECS.get(subcategory, []))
    if difficulty:
        pairs = [(s, d) for s, d in pairs if d == difficulty]
    return pairs


def all_specs_for(subcategory: str) -> list:
    """Search plan for a subcategory: explicit specs + generated easy-biased ones.

    Easy-biased specs run right after the primary relevance spec so their results
    are not crowded out by the per-subcategory candidate cap. They re-query the
    primary phrase sorted by votes (popularity) and with 'how to fix' phrasing,
    which surfaces short, straightforward questions needed to balance cells.
    """
    specs = list(SUBCATEGORY_SPECS.get(subcategory, []))
    base_q = next((s.value for s in specs if s.kind == "q"), None)
    if base_q and specs:
        easy_specs = [SearchSpec("q", base_q, "votes", bias="easy"),
                      SearchSpec("q", f"how to fix {base_q}", "votes", bias="easy")]
        return [specs[0]] + easy_specs + specs[1:]
    return specs


def validate_subcategory(name: str) -> bool:
    return name in SUBCATEGORY_TO_CATEGORY
