from fastapi import FastAPI
import os
import requests

app = FastAPI()


@app.get("/")
def health():
    return {"status": "ok"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/trigger")
def trigger():
    github_token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")  # format: owner/repo
    workflow = os.getenv("GITHUB_WORKFLOW")  # filename or ID

    if not github_token or not repo or not workflow:
        return {
            "status": "error",
            "message": "Missing required environment variables"
        }

    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches"

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json"
        },
        json={"ref": "main"}
    )

    return {
        "status": "triggered",
        "github_status": response.status_code
    }
