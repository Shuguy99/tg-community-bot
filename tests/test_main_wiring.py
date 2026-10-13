from app.main import install_middlewares


def test_install_middlewares_registers_expected():
    class _Reg:
        def __init__(self, sink):
            self.sink = sink

        def outer_middleware(self, mw):
            self.sink.append(mw)
            return mw

    class DP:
        def __init__(self):
            self.outer = []
            self.inner = []
            self.message = _Reg(self.outer)
            self.chat_member = _Reg(self.outer)

    class BotStub:
        pass

    class MwStub:
        pass

    dp = DP()
    install_middlewares(dp, MwStub(), MwStub(), MwStub())
    assert len(dp.outer) == 5
