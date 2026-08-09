import threading
from queue import Queue
from utils.log import timing_recorder
from utils.tts_ali_cosyvoice import tts

END_SIGNAL = "#stop tts#"


class TTSQueueManager:
    """TTS 队列管理器，确保 TTS 按顺序执行且不会并发"""

    def __init__(self, tts_callback=None):
        self.queue = Queue()
        self.tts_callback = tts_callback
        self.worker_thread = None
        self.is_running = False

    def start(self):
        """启动 TTS 工作线程"""
        if not self.is_running:
            self.is_running = True
            self.worker_thread = threading.Thread(
                target=self._process_queue, daemon=False
            )
            self.worker_thread.start()

    def stop(self):
        timing_recorder.stop = True
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except:
                break

    def add_sentence(self, sentence):
        """添加句子到 TTS 队列"""
        if sentence.strip():
            self.queue.put(sentence)

    def _process_queue(self):
        """处理 TTS 队列中的句子"""
        while self.is_running:
            try:
                sentence = self.queue.get(timeout=1)
                if sentence == END_SIGNAL:  # 结束信号
                    self.is_running = False
                    break
                if self.tts_callback:
                    self.tts_callback(sentence)
            except:
                continue


_tts_queue_manager_instance = None
_lock = threading.Lock()


def get_tts_manager() -> TTSQueueManager:
    """单例模式获取 TTSQueueManager 实例"""
    global _tts_queue_manager_instance
    if _tts_queue_manager_instance is None:
        with _lock:
            # 双重检查锁定模式
            if _tts_queue_manager_instance is None:
                _tts_queue_manager_instance = TTSQueueManager(tts_callback=tts)
                _tts_queue_manager_instance.start()
    return _tts_queue_manager_instance
