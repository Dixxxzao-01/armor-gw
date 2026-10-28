"""StrategyBandit：初始化 / 抽样 / 反馈持久化 / 先验注入的边界。"""
import os
import tempfile

from app.core.strategy_bandit import FAMILIES, StrategyBandit

MODEL = "m"


def test_new_path_empty_data():
    # 新路径初始化：data 为空 dict
    with tempfile.TemporaryDirectory() as d:
        b = StrategyBandit(os.path.join(d, "strategy_bandit.json"))
        assert b.data == {}


def test_pick_returns_valid_family():
    with tempfile.TemporaryDirectory() as d:
        b = StrategyBandit(os.path.join(d, "strategy_bandit.json"))
        assert b.pick(MODEL) in FAMILIES


def test_feedback_updates_arm_and_creates_file():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "strategy_bandit.json")
        b = StrategyBandit(path)
        fam = b.pick(MODEL)
        b.feedback(MODEL, fam, win=True)
        # 对应臂 wins+1
        assert b.data[MODEL][fam][0] == 1
        assert b.data[MODEL][fam][1] == 0
        # 持久化文件已生成
        assert os.path.isfile(path)


def test_reload_preserves_data():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "strategy_bandit.json")
        b1 = StrategyBandit(path)
        fam = b1.pick(MODEL)
        b1.feedback(MODEL, fam, win=True)
        b1.feedback(MODEL, fam, win=True)
        b2 = StrategyBandit(path)
        assert b2.data[MODEL][fam] == [2, 0]


def test_seed_prior_ignored_on_warmed_arm():
    # 先 feedback 两次（w+l >= 2），再 seed_prior 应无效
    with tempfile.TemporaryDirectory() as d:
        b = StrategyBandit(os.path.join(d, "strategy_bandit.json"))
        fam = "persona"
        b.feedback(MODEL, fam, win=True)
        b.feedback(MODEL, fam, win=True)
        b.seed_prior(MODEL, fam, 0.9)
        assert b.data[MODEL][fam] == [2, 0]


def test_seed_prior_applies_on_blank_arm():
    # 对照组：空白臂上先验生效（w 增加不低于注入值）
    with tempfile.TemporaryDirectory() as d:
        b = StrategyBandit(os.path.join(d, "strategy_bandit.json"))
        fam = "encoding"
        b.seed_prior(MODEL, fam, 0.5)
        assert b.data[MODEL][fam][0] == 2  # int(0.5 * 4)
