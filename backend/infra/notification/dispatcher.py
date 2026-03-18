from infra.notification.email_sender import EmailSender
from infra.notification.wecom_sender import WecomSender
from infra.notification.dingtalk_sender import DingtalkSender


class Dispatcher:
    def __init__(self):
        self._senders = {
            "email": EmailSender(),
            "wecom": WecomSender(),
            "dingtalk": DingtalkSender(),
        }

    async def dispatch(self, channel: str, message: str) -> None:
        sender = self._senders.get(channel)
        if sender:
            await sender.send(message)
