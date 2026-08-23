"""Tests de la résolution des chemins runtime (``chess_coach.bin.paths``)."""

from pathlib import Path

import pytest

from chess_coach.bin.paths import (
    CONFIG_FILENAME,
    default_state_dir,
    ensure_user_config,
    packaged_config_path,
    resolve_config_path,
    resolve_path,
)


def test_default_state_dir_utilise_localappdata_quand_defini(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_state_dir() == tmp_path / "chess_coach"


def test_default_state_dir_repli_sur_home_sans_localappdata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert default_state_dir().parts[-3:] == (".local", "share", "chess_coach")


def test_resolve_path_cli_prioritaire_sur_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CHESS_COACH_PLANS_DIR", str(tmp_path / "depuis_env"))
    result = resolve_path(
        str(tmp_path / "depuis_cli"), "CHESS_COACH_PLANS_DIR", tmp_path / "defaut"
    )
    assert result == tmp_path / "depuis_cli"


def test_resolve_path_env_prioritaire_sur_defaut(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CHESS_COACH_PLANS_DIR", str(tmp_path / "depuis_env"))
    result = resolve_path(None, "CHESS_COACH_PLANS_DIR", tmp_path / "defaut")
    assert result == tmp_path / "depuis_env"


def test_resolve_path_defaut_quand_rien_de_defini(tmp_path: Path) -> None:
    assert resolve_path(None, "CHESS_COACH_PLANS_DIR", tmp_path / "d") == tmp_path / "d"


def test_resolve_path_ignore_une_valeur_env_vide(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CHESS_COACH_PLANS_DIR", "   ")
    assert resolve_path(None, "CHESS_COACH_PLANS_DIR", tmp_path / "d") == tmp_path / "d"


def test_resolve_config_path_utilise_chess_coach_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cible = tmp_path / "ailleurs" / "mon_profil.yaml"
    monkeypatch.setenv("CHESS_COACH_CONFIG", str(cible))
    assert resolve_config_path() == cible


def test_resolve_config_path_derive_de_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CHESS_COACH_DATA_DIR", str(tmp_path))
    assert resolve_config_path() == tmp_path / CONFIG_FILENAME


def test_ensure_user_config_copie_le_modele_au_premier_lancement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cible = tmp_path / "etat" / CONFIG_FILENAME
    monkeypatch.setenv("CHESS_COACH_CONFIG", str(cible))
    assert not cible.exists()

    result = ensure_user_config()

    assert result == cible
    assert cible.exists()
    assert cible.read_text(encoding="utf-8") == packaged_config_path().read_text(
        encoding="utf-8"
    )


def test_ensure_user_config_n_ecrase_jamais_un_fichier_existant(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cible = tmp_path / CONFIG_FILENAME
    cible.write_text('player:\n  name: "Dupont"\n  elo: 1650\n', encoding="utf-8")
    monkeypatch.setenv("CHESS_COACH_CONFIG", str(cible))

    ensure_user_config()

    assert "Dupont" in cible.read_text(encoding="utf-8")


def test_packaged_config_path_existe_dans_le_package() -> None:
    """Le modèle packagé doit être livré : sans lui, pas d'amorçage possible."""
    assert packaged_config_path().is_file()
