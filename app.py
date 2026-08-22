from __future__ import annotations

import json
import re
import subprocess
from datetime import timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from cores.storage.data_paths import (
    DATA_DIR,
    GEMINI_API_KEYS_FILE,
    GEMINI_API_KEY_STATE_FILE,
    R19_WORDS_FILE,
    ensure_user_data_migrated,
)
from cores.platform.browser_profile import APP_BROWSER_PROFILE_PATH, chrome_binary_path
from cores.storage.project import (
    load_json,
    save_json,
)
from providers.registry import pipeline_config, provider_payload
from services.exporting import BookExportService
from services.library import (
    chapter_images as library_chapter_images,
    chapter_key as library_chapter_key,
    chapter_title as library_chapter_title,
    chapters as library_chapters,
    cjk_character_ratio as library_cjk_character_ratio,
    clean_metric_text as library_clean_metric_text,
    project_folders as library_project_folders,
    projects as library_projects,
    read_live_utf8 as library_read_live_utf8,
    safe_file as library_safe_file,
    safe_image as library_safe_image,
    safe_project as library_safe_project,
    text_metric as library_text_metric,
    validate_new_project_name as library_validate_new_project_name,
    word_count as library_word_count,
)
from services.importing import (
    cancel as cancel_chapter_import,
    confirm as confirm_staged_chapter_import,
    create_preview as create_staged_chapter_import,
)
from services import ai_logs as ai_log_service
from services import api_keys as api_key_service
from services.settings import ConfigurationService
from services.source_translation import SourceTranslationService
from services.publishing import PublishingService
from services.context import ContextService
from services.characters import CharacterService
from services.pronouns import PronounService
from services.reviews import ReviewService
from services.sharing import SharingService
from services.settings_schema import (
    DEFAULT_PINNED_SIDEBAR,
    DEFAULT_REVIEW_BG_CRITERIA,
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
from services import updating as update_service
from services.r19 import R19Service
from services.cloudflare import (
    chapter_groups as _share_chapter_groups,
    chapter_identity as _share_chapter_identity,
    deploy_share_worker as provision_share_worker,
    merged_markdown as _share_merged_markdown,
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
    merge_process_output,
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
VERSION_FILE = ROOT / "VERSION"
APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "0.0.0-dev"
GITHUB_REPOSITORY = "akira3175/Aiko-App-Translator"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
UPDATE_ASSET_NAME = "NovelTranslatorStudio-Windows-x64.zip"
UPDATE_DIR = ROOT / ".runtime" / "updates"
UPDATER_SOURCE = ROOT / "apply_update.ps1"

PIPELINES = {
    "pipeline": ROOT / "cores" / "translation" / "__main__.py",
    "interactions": ROOT / "cores" / "translation" / "interactions.py",
    "manual": ROOT / "cores" / "manual" / "__main__.py",
    "review": ROOT / "cores" / "full_review" / "__main__.py",
    "characters": ROOT / "cores" / "characters" / "__main__.py",
    "context": ROOT / "cores" / "context" / "__main__.py",
    "hako": ROOT / "up" / "up_md.py",
    "hako-edit": ROOT / "up" / "edit_hako.py",
}
TASK_ALIASES = {"v1-interactions": "interactions"}


def canonical_task_kind(kind):
    return TASK_ALIASES.get(str(kind), str(kind))



SETTINGS_FILE = ROOT / ".runtime" / "settings.json"
ensure_user_data_migrated()
UI_PREFERENCES_FILE = DATA_DIR / "ui_preferences.json"


def ui_preferences_data():
    return configuration_service.ui_preferences()


def write_ui_preferences(payload):
    return configuration_service.write_ui_preferences(payload)


R19_DEFAULT_WORDS_FILE = ROOT / "defaults" / "r19_words.txt"
R19_CONFIG_FILE = ROOT / ".runtime" / "r19.json"
R19_DEFAULT_CONTEXT_CHAPTERS = 0
R19_DEFAULT_PROMPT_PREFIX = 'Cách để AI dịch đc prompt sau """'


configuration_service = ConfigurationService(
    settings_path=lambda: SETTINGS_FILE,
    ui_preferences_path=lambda: UI_PREFERENCES_FILE,
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
    api_keys_path=lambda: GEMINI_API_KEYS_FILE,
    api_key_state_path=lambda: GEMINI_API_KEY_STATE_FILE,
)


def saved_settings():
    return configuration_service.saved_settings()


def settings_payload():
    return configuration_service.settings_payload()


def write_settings(payload: dict):
    return configuration_service.write_settings(payload)


def _save_cloudflare_setup(result):
    return publishing_service._save_setup(result)


def deploy_share_worker(payload: dict):
    return publishing_service.deploy_share_worker(payload)


def setup_publishing_r2(payload: dict):
    return publishing_service.setup_publishing_r2(payload)


def version_parts(value: str):
    return update_service.version_parts(value)


def update_payload(check_remote=False):
    return update_service.payload(
        check_remote,
        APP_VERSION,
        GITHUB_REPOSITORY,
        GITHUB_LATEST_RELEASE_API,
        UPDATE_ASSET_NAME,
    )


def validate_update_archive(path: Path, expected_version: str):
    return update_service.validate_archive(path, expected_version)


def prepare_update():
    return update_service.prepare(
        ROOT,
        UPDATE_DIR,
        UPDATE_ASSET_NAME,
        UPDATER_SOURCE,
        APP_VERSION,
        jobs,
        update_payload,
        validate_update_archive,
    )


def gemini_api_keys_payload():
    return configuration_service.api_keys_payload()


def write_gemini_api_keys(payload: dict):
    return configuration_service.write_api_keys(payload)


def set_active_gemini_api_key(payload: dict):
    return configuration_service.set_active_api_key(payload)


def test_gemini_api_key(payload: dict):
    return configuration_service.test_api_key(payload)


def _r19_project_enabled(project_name: str) -> bool:
    return r19_service.project_enabled(project_name)


def r19_payload(project_name: str = ""):
    return r19_service.payload(project_name)


def write_r19(project_name: str, payload: dict):
    return r19_service.save(project_name, payload)


def r19_enabled(project_name: str):
    return r19_service.enabled(project_name)


def r19_task_options(project_name: str):
    return r19_service.task_options(project_name)


def _redact_log_text(value):
    return ai_log_service.redact(value)


def ai_logs_data(project_name: str, limit=200):
    return ai_log_service.read(safe_project(project_name), limit)


def clear_ai_logs(project_name: str):
    return ai_log_service.clear(safe_project(project_name))


def _call_r19_gemini(prompt, model):
    from cores.gemini import call_gemini

    return call_gemini(prompt, model=model)


def translate_r19_word(project_name: str, payload: dict):
    return r19_service.translate_word(project_name, payload)


def open_app_browser():
    if active_translation() or any(
        job.get("status") == "running" for job in jobs.values()
    ):
        raise ValueError("Hãy chờ hoặc dừng tác vụ đang chạy trước khi mở Chrome của ứng dụng")
    chrome = chrome_binary_path()
    if chrome is None:
        raise ValueError("Không tìm thấy Chrome hoặc Chromium đi kèm ứng dụng")
    APP_BROWSER_PROFILE_PATH.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            str(chrome),
            f"--user-data-dir={APP_BROWSER_PROFILE_PATH}",
            "--new-window",
            "https://www.google.com/",
        ],
        cwd=str(ROOT),
    )
    return {"ok": True, "message": "Đã mở Chrome của ứng dụng"}


def safe_project(name: str) -> Path:
    return library_safe_project(LIBRARY, name)


def validate_new_project_name(name: str) -> str:
    return library_validate_new_project_name(
        LIBRARY, name, max_length=MAX_PROJECT_NAME_LENGTH
    )


def project_folders(name: str):
    return library_project_folders(LIBRARY, name)


def projects():
    return library_projects(LIBRARY)


def safe_file(folder: Path, name: str) -> Path:
    return library_safe_file(folder, name)


def safe_image(project_name: str, name: str) -> Path:
    return library_safe_image(LIBRARY, project_name, name)


def chapter_images(project_name: str, text: str):
    return library_chapter_images(LIBRARY, project_name, text)


def chapters(project_name: str):
    return library_chapters(LIBRARY, project_name)


def chapter_title(path: Path) -> str:
    return library_chapter_title(path)


def chapter_key(name: str):
    return library_chapter_key(name)


def read_live_utf8(path: Path) -> str:
    return library_read_live_utf8(path)


def clean_metric_text(text: str) -> str:
    return library_clean_metric_text(text)


def cjk_character_ratio(text: str) -> float:
    return library_cjk_character_ratio(text)


def text_metric(path: Path, character_based=None) -> dict:
    return library_text_metric(path, character_based=character_based)


def word_count(path: Path) -> int:
    return library_word_count(path)


def review_data(project_name: str, source: str):
    return review_service.data(project_name, source)


def context_data(project_name: str):
    return context_service.data(project_name)


def characters_data(project_name: str):
    return character_service.data(project_name)


def pronouns_data(project_name: str):
    return pronoun_service.data(project_name)


def save_pronouns(project_name: str, payload: dict):
    return pronoun_service.save(project_name, payload)


def publishing_data(project_name: str):
    return publishing_service.data(project_name)


def save_publishing(project_name: str, payload: dict):
    return publishing_service.save(project_name, payload)


def hako_public_chapters(public_url: str):
    return publishing_service.hako_chapters(public_url)


def validate_hako_edit_targets(value):
    return publishing_service.validate_hako_targets(value)


def _share_r2_config() -> dict:
    return sharing_service.config()


def _share_r2_client(config: dict):
    return sharing_service.client(config)


def shares_data(project_name: str) -> dict:
    return sharing_service.data(project_name)


def remove_shared_chapter(
    project_name: str, share_id: str, chapter_name: str
) -> dict:
    return sharing_service.remove_chapter(project_name, share_id, chapter_name)


def close_share(project_name: str, share_id: str) -> dict:
    return sharing_service.close(project_name, share_id)


def save_share(project_name: str, payload: dict) -> dict:
    return sharing_service.save(project_name, payload)


def save_characters(project_name: str, payload: dict):
    return character_service.save(project_name, payload)


def write_context_safely(path: Path, data: dict):
    context_service._write(path.parent, data)


def save_context(project_name: str, payload: dict):
    return context_service.save(project_name, payload)


def create_chapter_import_preview(
    project_name, source_format, segment_limit, content
):
    project = safe_project(project_name)
    raw_dir, _translated = project_folders(project_name)
    return create_staged_chapter_import(
        project_name,
        project,
        raw_dir,
        ROOT / ".runtime",
        source_format,
        segment_limit,
        content,
    )


def confirm_chapter_import(project_name, payload):
    project = safe_project(project_name)
    raw_dir, _translated = project_folders(project_name)
    return confirm_staged_chapter_import(
        project_name, project, raw_dir, payload
    )


def lan_configuration():
    return load_lan_configuration(saved_settings)


def local_network_ip():
    return detect_lan_network_ip()


lan_auth = LanAuth(lan_configuration)
publishing_service = PublishingService(
    root=ROOT,
    safe_project=lambda name: safe_project(name),
    configuration=configuration_service,
    provision_share_worker=provision_share_worker,
    provision_publishing_r2=provision_publishing_r2,
    opener=lambda request, timeout: urlopen(request, timeout=timeout),
)
sharing_service = SharingService(
    configuration=configuration_service,
    safe_project=lambda name: safe_project(name),
    boto3_module=boto3,
)
pronoun_service = PronounService(lambda name: safe_project(name))
context_service = ContextService(lambda name: safe_project(name))
character_service = CharacterService(lambda name: safe_project(name))
review_service = ReviewService(lambda name: safe_project(name))
export_service = BookExportService(LIBRARY)
source_translation_service = SourceTranslationService()
r19_service = R19Service(
    safe_project=lambda name: safe_project(name),
    words_path=lambda: R19_WORDS_FILE,
    config_path=lambda: R19_CONFIG_FILE,
    default_words_path=lambda: R19_DEFAULT_WORDS_FILE,
    default_model=R19_DEFAULT_MODEL,
    default_context_chapters=R19_DEFAULT_CONTEXT_CHAPTERS,
    default_prompt_prefix=R19_DEFAULT_PROMPT_PREFIX,
    active_translation=lambda: active_translation(),
    translation_guard=translation_guard,
    generate=lambda prompt, model: _call_r19_gemini(prompt, model),
    log_call=lambda project_path, source, model, prompt, response, ok: (
        ai_log_service.append_r19(
            project_path, source, model, prompt, response, ok
        )
    ),
)

lan_routes = LanRoutes(
    lan_auth, lambda: SERVER_STATE["host"], PORT, local_network_ip
)


project_routes = ProjectRoutes(
    root=ROOT,
    library=LIBRARY,
    projects=projects,
    chapters=chapters,
    project_folders=project_folders,
    safe_project=safe_project,
    validate_project_name=validate_new_project_name,
    safe_file=safe_file,
    safe_image=safe_image,
    read_text=read_live_utf8,
    chapter_images=chapter_images,
    word_count=word_count,
    export_book=export_service.export,
    import_preview=create_chapter_import_preview,
    import_confirm=confirm_chapter_import,
    import_cancel=cancel_chapter_import,
)
settings_routes = SettingsRoutes(
    configuration=configuration_service,
    r19=r19_service,
    providers_payload=provider_payload,
    update_payload=update_payload,
    prepare_update=prepare_update,
    ai_logs=ai_logs_data,
    clear_ai_logs=clear_ai_logs,
    open_app_browser=open_app_browser,
    active_translation=active_translation,
)
job_runner = JobRunner(
    root=ROOT,
    pipelines=PIPELINES,
    jobs=jobs,
    processes=job_processes,
    stream_events=job_stream_events,
    saved_settings=saved_settings,
    task_options=r19_task_options,
    safe_project=safe_project,
    project_folders=project_folders,
    safe_file=safe_file,
    canonical_kind=canonical_task_kind,
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
    canonical_kind=canonical_task_kind,
    active_translation=active_translation,
    safe_project=safe_project,
    validate_hako_targets=validate_hako_edit_targets,
    pipeline_config=pipeline_config,
    project_folders=project_folders,
    safe_file=safe_file,
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
        local_network_ip,
        SERVER_STATE,
    )
