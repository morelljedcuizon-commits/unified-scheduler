"""Run blocking provider work away from the GUI thread."""
from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.function()
        except Exception as exc:
            # Providers expose sanitized messages. Never forward raw transport errors.
            from unified_scheduler.providers.errors import ProviderError
            if isinstance(exc, ProviderError):
                message = str(exc)
            else:
                message = "The operation could not finish. Check your connection and credential store, then try again."
            self.signals.failed.emit(message)
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()
