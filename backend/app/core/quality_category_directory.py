"""Reference documents for older categories; not an allowed-category list."""

LOCAL_URL = "https://www.cqck.gov.cn/bm/scjgj/zwgk_70831/fdzdgknr_70834/cpzl/jcyj/202605/t20260526_15703868.html"
NATIONAL_URL = "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/zljds/art/2024/art_74e90827bbe044dfaccb05848f4d4812.html"
LOCAL_TITLE = "城口县2026年产品质量监督抽查实施细则公告"

DIRECTORY = tuple({"key": key, "name": name, "source_title": LOCAL_TITLE, "source_url": LOCAL_URL}
    for key, name in [
        ("electric_bicycle", "电动自行车"),
        ("electric_bicycle_charger", "电动自行车充电器"),
        ("wire_cable", "电线电缆"),
        ("automotive_urea", "车用尿素"),
        ("liquefied_petroleum_gas", "液化石油气"),
        ("wood_based_panel", "人造板"),
        ("gas_appliance_hose", "燃气用具连接用软管"),
        ("school_uniform", "校服"),
        ("steel_wire_rope", "钢丝绳"),
        ("portable_gas_stove", "卡式炉"),
        ("raw_lacquer", "生漆"),
        ("disposable_plastic_tableware", "塑料一次性餐饮具"),
        ("food_contact_paper_container", "食品接触用纸容器"),
        ("jewelry", "珠宝首饰"),
    ]) + ({"key": "electric_bicycle_battery", "name": "电动自行车电池",
           "source_title": "市场监管总局电动自行车、电动自行车电池监督抽查实施细则公告", "source_url": NATIONAL_URL},)
BY_KEY = {item["key"]: item for item in DIRECTORY}
BY_NAME = {item["name"]: item for item in DIRECTORY}


def reference_basis(name):
    item = BY_NAME.get(name)
    return f'{item["source_title"]}；产品项：{name}；{item["source_url"]}' if item else None
