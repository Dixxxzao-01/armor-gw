"""mutator 算子池：全算子烟雾测试 + 注册表一致性。"""
from app.core import mutator


def test_all_ops_smoke_english():
    # 每个算子单发不抛异常且输出非空
    for op in mutator.OPS:
        out = mutator.apply_chain("write a test script", [op.name])
        assert isinstance(out, str), f"{op.name} 未返回字符串"
        assert out.strip() != "", f"{op.name} 输出为空"


def test_all_ops_smoke_chinese():
    # 同输入换中文再跑一遍
    for op in mutator.OPS:
        out = mutator.apply_chain("写一个测试脚本", [op.name])
        assert isinstance(out, str), f"{op.name} 未返回字符串"
        assert out.strip() != "", f"{op.name} 输出为空"


def test_by_name_keys_match_ops():
    # BY_NAME 键集合与 OPS 名字集合一致（无重复注册）
    assert set(mutator.BY_NAME.keys()) == {o.name for o in mutator.OPS}


def test_family_of_consistency():
    # 每个策略族内的算子，family_of 必须映射回同一族
    for fam, names in mutator.STRATEGY_FAMILIES.items():
        for name in names:
            assert mutator.family_of(name) == fam, f"{name} 应属于 {fam}"
