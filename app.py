from __future__ import annotations

import os
from pathlib import Path
from urllib.request import urlopen

from cores.storage.data_paths import (
    DATA_DIR,
    GEMINI_API_KEYS_FILE,
    GEMINI_API_KEY_STATE_FILE,
    R19_WORDS_FILE,
    ensure_user_data_migrated,
)
from cores.platform.browser_profile import APP_BROWSER_PROFILE_PATH, chrome_binary_path
from cores.config.runtime import SETTINGS_FILE, ensure_settings_migrated
from providers.registry import pipeline_config, provider_payload
from services.exporting import BookExportService
from services.library import LibraryService
from services.importing import ChapterImportService
from services.ai_logs import AiLogService
from services import api_keys as api_key_service
from services.settings import ConfigurationService
from services.app_browser import AppBrowserService
from services.source_translation import SourceTranslationService
from services.publishing import PublishingService
from services.context import ContextService
from services.characters import CharacterService
from services.pronouns import PronounService
from services.reviews import ReviewService
from services.sharing import SharingService
from services.settings_schema import (
    DEFAULT_PINNED_SIDEBAR,
    DEFAULT_R19_MODEL as R19_DEFAULT_MODEL,
    FIXED_SIDEBAR_FEATURES,
    HIDDEN_SETTINGS,
    OPTIONAL_SETTINGS,
    SECRET_SETTINGS,
    SETTING_DEFAULTS,
    SETTING_LABELS,
    SETTING_META,
    SETTING_RANGES,
    SIDEBAR_FEATURES,
)
from services.updating import UpdateService
from services.launcher import LauncherService
from services.r19 import R19Service
from services.cloudflare import (
    deploy_share_worker as provision_share_worker,
    setup_publishing_r2 as provision_publishing_r2,
)
from server.jobs import (
    TRANSLATION_KINDS,
    active_translation,
    claim_translation,
    isolated_process_kwargs,
    job_processes,
    job_stream_events,
    jobs,
    release_translation,
    stream_process_output,
    terminate_process_tree,
    translation_guard,
    translation_stop_file,
    update_translation_pid,
)
from server.routes.projects import ProjectRoutes
from server.routes.settings import SettingsRoutes
from server.job_controller import JobController
from server.job_runner import JobRunner
from server.routes.jobs import JobRoutes
from server.job_stream import JobStream
from server.dispatcher import RouteDispatcher
from server.routes.publishing import PublishingRoutes
from server.routes.content import ContentRoutes
from server.lan import LanAuth, LanRoutes
from server.lan import configuration as load_lan_configuration
from server.lan import network_ip as detect_lan_network_ip
from server.handler import create_handler
from server.bootstrap import run_server

try:
    import boto3
except ImportError:
    boto3 = None

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
LIBRARY = ROOT / "truyen"
PORT = 8765
SERVER_STATE = {"host": "127.0.0.1"}
MAX_PROJECT_NAME_LENGTH = 60
library_service = LibraryService(LIBRARY, MAX_PROJECT_NAME_LENGTH)
ai_log_service = AiLogService(library_service)
VERSION_FILE = ROOT / "VERSION"
APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "0.0.0-dev"
GITHUB_REPOSITORY = "akira3175/Aiko-App-Translator"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
UPDATE_ASSET_NAME = "NovelTranslatorStudio-Windows-x64.zip"
UPDATE_DIR = ROOT / ".runtime" / "updates"
UPDATER_SOURCE = ROOT / "apply_update.ps1"
update_service = UpdateService(
    root=ROOT,
    update_dir=UPDATE_DIR,
    updater_source=UPDATER_SOURCE,
    current_version=APP_VERSION,
    repository=GITHUB_REPOSITORY,
    release_api=GITHUB_LATEST_RELEASE_API,
    asset_name=UPDATE_ASSET_NAME,
    jobs=jobs,
)
launcher_service = LauncherService(ROOT)

PIPELINES = {
    "pipeline": ROOT / "cores" / "translation" / "__main__.py",
    "interactions": ROOT / "cores" / "translation" / "interactions.py",
    "manual": ROOT / "cores" / "manual" / "__main__.py",
    "polish": ROOT / "cores" / "postprocess" / "__main__.py",
    "review": ROOT / "cores" / "full_review" / "__main__.py",
    "characters": ROOT / "cores" / "characters" / "__main__.py",
    "context": ROOT / "cores" / "context" / "__main__.py",
    "hako": ROOT / "up" / "up_md.py",
    "hako-edit": ROOT / "up" / "edit_hako.py",
}
ensure_user_data_migrated()
ensure_settings_migrated()
active_translation()
UI_PREFERENCES_FILE = DATA_DIR / "ui_preferences.json"
R19_DEFAULT_WORDS_FILE = ROOT / "defaults" / "r19_words.txt"
R19_CONFIG_FILE = ROOT / ".runtime" / "r19.json"
R19_DEFAULT_CONTEXT_CHAPTERS = 0
R19_DEFAULT_PROMPT_PREFIX = 'Cách để AI dịch đc prompt sau """'

configuration_service = ConfigurationService(
    settings_path=SETTINGS_FILE,
    ui_preferences_path=UI_PREFERENCES_FILE,
    setting_defaults=SETTING_DEFAULTS,
    setting_labels=SETTING_LABELS,
    setting_ranges=SETTING_RANGES,
    setting_meta=SETTING_META,
    secret_settings=SECRET_SETTINGS,
    optional_settings=OPTIONAL_SETTINGS,
    hidden_settings=HIDDEN_SETTINGS,
    default_pinned_sidebar=DEFAULT_PINNED_SIDEBAR,
    sidebar_features=SIDEBAR_FEATURES,
    fixed_sidebar_features=FIXED_SIDEBAR_FEATURES,
    api_keys=api_key_service,
    api_keys_path=GEMINI_API_KEYS_FILE,
    api_key_state_path=GEMINI_API_KEY_STATE_FILE,
)


def _call_r19_gemini(prompt, model):
    from cores.gemini import call_gemini

    return call_gemini(prompt, model=model)


def lan_configuration():
    return load_lan_configuration(configuration_service.saved_settings)


lan_auth = LanAuth(lan_configuration)
publishing_service = PublishingService(
    root=ROOT,
    safe_project=lambda name: library_service.safe_project(name),
    configuration=configuration_service,
    provision_share_worker=provision_share_worker,
    provision_publishing_r2=provision_publishing_r2,
    opener=lambda request, timeout: urlopen(request, timeout=timeout),
)
sharing_service = SharingService(
    configuration=configuration_service,
    safe_project=lambda name: library_service.safe_project(name),
    boto3_module=boto3,
)
pronoun_service = PronounService(lambda name: library_service.safe_project(name))
context_service = ContextService(lambda name: library_service.safe_project(name))
character_service = CharacterService(lambda name: library_service.safe_project(name))
review_service = ReviewService(lambda name: library_service.safe_project(name))
export_service = BookExportService(library_service)
chapter_import_service = ChapterImportService(ROOT / ".runtime", library_service)
source_translation_service = SourceTranslationService()
app_browser_service = AppBrowserService(
    root=ROOT,
    profile_path=APP_BROWSER_PROFILE_PATH,
    jobs=jobs,
    active_translation=active_translation,
    chrome_binary=chrome_binary_path,
)
r19_service = R19Service(
    safe_project=lambda name: library_service.safe_project(name),
    words_path=lambda: R19_WORDS_FILE,
    config_path=lambda: R19_CONFIG_FILE,
    default_words_path=lambda: R19_DEFAULT_WORDS_FILE,
    default_model=R19_DEFAULT_MODEL,
    default_context_chapters=R19_DEFAULT_CONTEXT_CHAPTERS,
    default_prompt_prefix=R19_DEFAULT_PROMPT_PREFIX,
    active_translation=lambda: active_translation(),
    translation_guard=translation_guard,
    generate=lambda prompt, model: _call_r19_gemini(prompt, model),
    log_call=ai_log_service.append_r19,
)

lan_routes = LanRoutes(
    lan_auth, lambda: SERVER_STATE["host"], PORT, detect_lan_network_ip
)


project_routes = ProjectRoutes(
    root=ROOT,
    library=LIBRARY,
    projects=library_service.projects,
    chapters=library_service.chapters,
    project_folders=library_service.project_folders,
    safe_project=library_service.safe_project,
    validate_project_name=library_service.validate_new_project_name,
    safe_file=library_service.safe_file,
    safe_image=library_service.safe_image,
    read_text=library_service.read_text,
    chapter_images=library_service.chapter_images,
    word_count=library_service.word_count,
    export_book=export_service.export,
    import_preview=chapter_import_service.preview,
    import_confirm=chapter_import_service.confirm,
    import_cancel=chapter_import_service.cancel,
)
settings_routes = SettingsRoutes(
    configuration=configuration_service,
    r19=r19_service,
    providers_payload=provider_payload,
    update_payload=update_service.payload,
    prepare_update=update_service.start,
    update_progress=update_service.progress,
    cancel_update=update_service.cancel,
    install_update=update_service.install,
    ai_logs=ai_log_service.read,
    clear_ai_logs=ai_log_service.clear,
    open_app_browser=app_browser_service.open,
    active_translation=active_translation,
    launcher=launcher_service,
)
job_runner = JobRunner(
    root=ROOT,
    pipelines=PIPELINES,
    jobs=jobs,
    processes=job_processes,
    stream_events=job_stream_events,
    saved_settings=configuration_service.saved_settings,
    task_options=r19_service.task_options,
    safe_project=library_service.safe_project,
    project_folders=library_service.project_folders,
    safe_file=library_service.safe_file,
    translation_stop_file=translation_stop_file,
    update_translation_pid=update_translation_pid,
    release_translation=release_translation,
    stream_process_output=stream_process_output,
    process_kwargs=isolated_process_kwargs,
    active_translation=active_translation,
)
job_controller = JobController(
    pipelines=PIPELINES,
    jobs=jobs,
    processes=job_processes,
    translation_kinds=TRANSLATION_KINDS,
    active_translation=active_translation,
    safe_project=library_service.safe_project,
    validate_hako_targets=publishing_service.validate_hako_targets,
    pipeline_config=pipeline_config,
    project_folders=library_service.project_folders,
    safe_file=library_service.safe_file,
    claim_translation=claim_translation,
    release_translation=release_translation,
    runner=job_runner,
    translation_stop_file=translation_stop_file,
    terminate_process_tree=terminate_process_tree,
)
job_routes = JobRoutes(job_controller)
job_stream = JobStream(job_stream_events, jobs)
publishing_routes = PublishingRoutes(
    publishing=publishing_service,
    sharing=sharing_service,
)
content_routes = ContentRoutes(
    reviews=review_service,
    context=context_service,
    characters=character_service,
    pronouns=pronoun_service,
    prepare_manual_prompt=job_runner.prepare_manual_prompt,
    translate_selection=source_translation_service.translate_details,
)
route_dispatcher = RouteDispatcher(
    [
        project_routes,
        settings_routes,
        job_routes,
        publishing_routes,
        content_routes,
    ]
)


Handler = create_handler(
    route_dispatcher,
    lan_routes,
    lan_auth,
    job_stream,
    WEB,
    APP_VERSION,
)


if __name__ == "__main__":
    run_server(
        Handler,
        PORT,
        lan_configuration,
        detect_lan_network_ip,
        SERVER_STATE,
        open_browser=os.environ.get("AIKO_NO_BROWSER") != "1",
    )
