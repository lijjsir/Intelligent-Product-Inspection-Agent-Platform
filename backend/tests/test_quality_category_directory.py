import pytest

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.schemas.quality_risk import CategoryImportConfirm, ProductCategoryCreate, ProductCategoryUpdate, ProductCreate
from app.services.quality_category_imports import preview_categories, confirm_categories
from test_quality_risk_v4 import domain  # noqa: F401


@pytest.mark.asyncio
async def test_admin_can_define_category_outside_reference_list_with_basis(domain):
    _, service = domain
    admin = service("admin")
    category = await admin.create_category(ProductCategoryCreate(name="工业紧固件", classification_basis="隔离验证分类目录，工业紧固件条目"))
    product = await admin.create_product(ProductCreate(category_id=category["id"], name="螺栓样品"))
    assert category["classification_basis"] == "隔离验证分类目录，工业紧固件条目"
    assert product["category_id"] == category["id"]
    duplicate = await admin.create_category(ProductCategoryCreate(name="工业紧固件", classification_basis="另一份依据"))
    assert duplicate["id"] == category["id"] and duplicate["classification_basis"] == category["classification_basis"]


@pytest.mark.asyncio
async def test_category_requires_meaningful_name_but_basis_can_be_supplemented(domain):
    _, service = domain
    for name, basis in [("1234", "验证依据"), ("@@@", "验证依据")]:
        with pytest.raises(ValidationError):
            await service("admin").create_category(ProductCategoryCreate(name=name, classification_basis=basis))
    with pytest.raises(ForbiddenError):
        await service("expert").create_category(ProductCategoryCreate(name="工业紧固件", classification_basis="验证依据"))
    draft = await service("admin").create_category(ProductCategoryCreate(name="工业紧固件"))
    assert draft["classification_basis"] is None
    known = await service("admin").create_category(ProductCategoryCreate(name="电线电缆"))
    assert known["classification_basis"] is None
    product = await service("admin").create_product(ProductCreate(category_id=draft["id"], name="螺栓"))
    assert product["category_id"] == draft["id"]


@pytest.mark.asyncio
async def test_category_edit_and_normalized_duplicates(domain):
    _, service = domain
    admin = service("admin")
    category = await admin.create_category(ProductCategoryCreate(name=" ＡＢＣ紧固件 ", classification_basis="验证依据"))
    duplicate = await admin.create_category(ProductCategoryCreate(name="ABC紧固件", classification_basis="验证依据"))
    assert duplicate["id"] == category["id"]
    updated = await admin.update_category(category["id"], ProductCategoryUpdate(name="工业紧固件", classification_basis="修订分类目录，紧固件条目"))
    assert updated["name"] == "工业紧固件" and updated["display_no"] == category["display_no"]
    other = await admin.create_category(ProductCategoryCreate(name="金属材料", classification_basis="验证目录材料条目"))
    with pytest.raises(ConflictError):
        await admin.update_category(other["id"], ProductCategoryUpdate(name="工业紧固件"))


@pytest.mark.asyncio
async def test_category_directory_import_and_duplicate_reuse(domain):
    _, service = domain
    svc = service("admin")
    content = "类别名称,分类依据\n工业紧固件,文件逐行依据\n金属材料,\n工业紧固件,文件逐行依据\n".encode("utf-8-sig")
    preview = await preview_categories(svc, "categories.csv", content, "共同分类目录")
    assert preview["can_confirm"] and preview["rows"][0]["classification_basis"] == "文件逐行依据"
    assert preview["rows"][1]["classification_basis"] == "共同分类目录"
    result = await confirm_categories(svc, CategoryImportConfirm(rows=preview["rows"]))
    assert result["created_count"] == 2 and result["reused_count"] == 1
    assert len((await svc.product_catalog())["categories"]) == 2


@pytest.mark.asyncio
async def test_import_revalidates_and_rolls_back_all_rows_on_invalid_definition(domain):
    _, service = domain
    svc = service("admin")
    preview = await preview_categories(svc, "categories.csv", "类别名称,分类依据\n1234,\n".encode("utf-8-sig"))
    assert not preview["can_confirm"] and preview["errors"]
    with pytest.raises(ValidationError):
        await confirm_categories(svc, CategoryImportConfirm(rows=[
            {"name": "工业紧固件", "classification_basis": "验证依据"}, {"name": "1234"}]))
    assert (await svc.product_catalog())["categories"] == []


@pytest.mark.asyncio
async def test_product_candidates_find_sparse_matches_but_do_not_merge(domain):
    db, service = domain
    admin = service("admin")
    category = await admin.create_category(ProductCategoryCreate(name="工业紧固件"))
    sparse = await admin.create_product(ProductCreate(category_id=category["id"], name="工业螺栓"))
    candidates = await admin.product_candidates(category["id"], "工业螺栓", brand="品牌甲", model="A1")
    assert candidates[0]["id"] == sparse["id"] and "型号" in candidates[0]["missing_fields"]
    assert len((await admin.product_catalog())["products"]) == 1
    from app.schemas.quality_risk import ProductUpdate
    await admin.update_product(sparse["id"], ProductUpdate(brand="品牌甲", model="A1"))
    assert await admin.product_candidates(category["id"], "工业螺栓", brand="品牌乙") == []
    from app.services.quality_risk_service import QualityRiskService
    from app.schemas.user import CurrentUser
    from test_quality_risk_v4 import uid
    foreign = QualityRiskService(db, CurrentUser(user_id=uid(), org_id=uid(), role="admin"))
    assert await foreign.product_candidates(category["id"], "工业螺栓") == []
    with pytest.raises(ForbiddenError):
        await service("expert").product_candidates(category["id"], "工业螺栓")
