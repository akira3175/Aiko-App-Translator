"""Application orchestration for private Cloudflare R2 shares."""

from services.cloudflare import sharing


class SharingService:
    def __init__(self, *, configuration, safe_project, boto3_module):
        self.configuration = configuration
        self._safe_project = safe_project
        self.boto3 = boto3_module

    def config(self):
        settings = {
            **self.configuration.setting_defaults,
            **self.configuration.saved_settings(),
        }
        config = {
            "account_id": str(settings.get("share_r2_account_id", "")).strip(),
            "access_key_id": str(
                settings.get("share_r2_access_key_id", "")
            ).strip(),
            "secret_access_key": str(
                settings.get("share_r2_secret_access_key", "")
            ).strip(),
            "bucket": str(settings.get("share_r2_bucket", "")).strip(),
            "worker_url": str(settings.get("share_worker_url", ""))
            .strip()
            .rstrip("/"),
        }
        required = ("account_id", "access_key_id", "secret_access_key", "bucket")
        if any(not config[key] for key in required):
            raise ValueError("Chưa cấu hình đầy đủ bucket R2 share private")
        return config

    def client(self, config):
        if self.boto3 is None:
            raise ValueError("Thiếu boto3; hãy cài requirements-portable.txt")
        return self.boto3.client(
            "s3",
            endpoint_url=(
                f"https://{config['account_id']}.r2.cloudflarestorage.com"
            ),
            aws_access_key_id=config["access_key_id"],
            aws_secret_access_key=config["secret_access_key"],
            region_name="auto",
        )

    def data(self, project_name):
        settings = {
            **self.configuration.setting_defaults,
            **self.configuration.saved_settings(),
        }
        worker_url = str(settings.get("share_worker_url", "")).strip().rstrip("/")
        return sharing.shares_data(
            self._safe_project(project_name),
            worker_url,
            bool(settings.get("share_r2_bucket")),
        )

    def remove_chapter(self, project_name, share_id, chapter_name):
        config = self.config()
        return sharing.remove_chapter(
            self._safe_project(project_name),
            share_id,
            chapter_name,
            config,
            self.client(config),
        )

    def close(self, project_name, share_id):
        config = self.config()
        return sharing.close(
            self._safe_project(project_name),
            share_id,
            config,
            self.client(config),
        )

    def save(self, project_name, payload):
        action = str(payload.get("action", "")).strip()
        share_id = str(payload.get("share_id", "")).strip()
        if action == "remove_chapter":
            return self.remove_chapter(
                project_name,
                share_id,
                str(payload.get("chapter", "")).strip(),
            )
        if action == "close":
            return self.close(project_name, share_id)
        config = self.config()
        return sharing.save(
            project_name,
            self._safe_project(project_name),
            payload,
            config,
            self.client(config),
        )
