import os

for _i, (_k, _v) in enumerate((
    ("diff.algorithm", "myers"), ("diff.context", "3"), ("diff.indentHeuristic", "true"),
    ("format.encodeEmailHeaders", "false"))):
    os.environ["GIT_CONFIG_KEY_%d" % _i] = _k
    os.environ["GIT_CONFIG_VALUE_%d" % _i] = _v
os.environ["GIT_CONFIG_COUNT"] = "4"
