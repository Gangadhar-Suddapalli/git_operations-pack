import os
import subprocess
import requests
from st2common.runners.base_action import Action

class GitPushEachPack(Action):
    def run(self, github_token, github_user_or_org):
        packs_dir = '/opt/stackstorm/packs'
        branch = 'main'
        github_api_url = 'https://api.github.com'

        if not os.path.isdir(packs_dir):
            self.logger.error("Packs directory not found.")
            return False

        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github+json'
        }

        for pack_name in os.listdir(packs_dir):
            pack_path = os.path.join(packs_dir, pack_name)
            if not os.path.isdir(pack_path):
                continue  # Skip non-directories

            repo_name = pack_name
            repo_url = f"https://github.com/{github_user_or_org}/{repo_name}.git"
            self.logger.info(f"Processing pack: {pack_name}")

            # Check if GitHub repo exists, create if not
            repo_check = requests.get(f"{github_api_url}/repos/{github_user_or_org}/{repo_name}", headers=headers)
            if repo_check.status_code == 404:
                self.logger.info(f"Repository '{repo_name}' not found. Creating...")
                create_resp = requests.post(f"{github_api_url}/user/repos" if github_user_or_org == self._get_authenticated_user(github_token) else f"{github_api_url}/orgs/{github_user_or_org}/repos",
                                            headers=headers,
                                            json={"name": repo_name, "private": False})
                if create_resp.status_code not in [201, 202]:
                    self.logger.error(f"Failed to create repo {repo_name}: {create_resp.text}")
                    continue
                self.logger.info(f"Repository '{repo_name}' created.")
            elif repo_check.status_code != 200:
                self.logger.error(f"Failed to check repo: {repo_check.text}")
                continue

            try:
                # Git safe directory
                subprocess.run(['git', 'config', '--global', '--add', 'safe.directory', pack_path], check=True)

                git_dir = os.path.join(pack_path, '.git')

                # Initialize Git if not already a repo
                if not os.path.isdir(git_dir):
                    self.logger.info(f"Initializing git repo in {pack_path}")
                    subprocess.run(['git', 'init', '-b', branch], cwd=pack_path, check=True)

                # Set or update remote origin
                remote_check = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=pack_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if remote_check.returncode == 0:
                    subprocess.run(['git', 'remote', 'set-url', 'origin', repo_url], cwd=pack_path, check=True)
                else:
                    subprocess.run(['git', 'remote', 'add', 'origin', repo_url], cwd=pack_path, check=True)

                # Add, commit, and push
                subprocess.run(['git', 'add', '--all'], cwd=pack_path, check=True)
                status = subprocess.run(['git', 'status', '--porcelain'], cwd=pack_path, stdout=subprocess.PIPE)
                if status.returncode == 0 and status.stdout:
                    subprocess.run(['git', 'commit', '-m', f'Update pack: {pack_name}'], cwd=pack_path, check=True)
                subprocess.run(['git', 'checkout', '-B', branch], cwd=pack_path, check=True)
                subprocess.run(['git', 'push', '-u', 'origin', branch], cwd=pack_path, check=True)

                self.logger.info(f"Pack '{pack_name}' pushed to GitHub repository '{repo_name}'.")

            except subprocess.CalledProcessError as e:
                self.logger.error(f"Git error for pack '{pack_name}': {e}")
            except Exception as e:
                self.logger.error(f"Unexpected error for pack '{pack_name}': {e}")

        return True

    def _get_authenticated_user(self, token):
        # Utility to determine if this is a user or org repo
        resp = requests.get('https://api.github.com/user', headers={
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github+json'
        })
        if resp.status_code == 200:
            return resp.json().get('login')
        return None
