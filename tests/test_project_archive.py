from app.core.content_projects import create_project, delete_project, list_projects, update_project


def test_delete_project_removes_only_target(tmp_path):
    path = tmp_path / "projects.json"
    keep = create_project("남길 프로젝트", path)
    drop = create_project("지울 프로젝트", path)
    assert delete_project(drop["id"], path) is True
    ids = [item["id"] for item in list_projects(path, include_archived=True)]
    assert ids == [keep["id"]]


def test_delete_project_unknown_id_returns_false(tmp_path):
    path = tmp_path / "projects.json"
    create_project("하나", path)
    assert delete_project("없는-id", path) is False
    assert len(list_projects(path)) == 1


def test_delete_project_missing_file(tmp_path):
    assert delete_project("x", tmp_path / "none.json") is False


def test_archived_filtered_by_default(tmp_path):
    path = tmp_path / "projects.json"
    shown = create_project("보이는 프로젝트", path)
    hidden = create_project("보관할 프로젝트", path)
    update_project(hidden["id"], {"archived": True}, path)
    assert [item["id"] for item in list_projects(path)] == [shown["id"]]
    assert {item["id"] for item in list_projects(path, include_archived=True)} == {shown["id"], hidden["id"]}


def test_restore_makes_project_visible_again(tmp_path):
    path = tmp_path / "projects.json"
    item = create_project("복원 대상", path)
    update_project(item["id"], {"archived": True}, path)
    assert list_projects(path) == []
    update_project(item["id"], {"archived": False}, path)
    assert [row["id"] for row in list_projects(path)] == [item["id"]]


def test_update_unknown_id_does_not_change_file(tmp_path):
    path = tmp_path / "projects.json"
    create_project("하나", path)
    assert update_project("없는-id", {"archived": True}, path) is None
    assert len(list_projects(path)) == 1
