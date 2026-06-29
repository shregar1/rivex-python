import time

from rivex import APIStatus, BackgroundTasks, Rivex

app = Rivex(title="Background Tasks Example")

audit_log: list[str] = []


def send_welcome_email(email: str) -> None:
    time.sleep(0.05)
    audit_log.append(f"sent welcome email to {email}")


def provision_workspace(email: str) -> None:
    time.sleep(0.02)
    audit_log.append(f"provisioned workspace for {email}")


@app.post("/signup/{email}", status_code=APIStatus.ACCEPTED)
async def signup(email: str, bg_tasks: BackgroundTasks):
    bg_tasks.add_task(send_welcome_email, email)
    bg_tasks.add_task(provision_workspace, email)
    return {"status": "accepted", "email": email}


@app.get("/audit")
async def audit():
    return {"log": list(audit_log)}


if __name__ == "__main__":
    app.run(port=8000)
