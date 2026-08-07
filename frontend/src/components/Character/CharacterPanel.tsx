import { useEffect, useState } from "react";
import { apiGet, apiPost, ApiError } from "../../api/client";
import type { BloodstainOut, CharacterOut, QuestlineOut } from "../../api/types";
import { useAppData } from "../../context/AppDataContext";
import { BloodstainBanner } from "./BloodstainBanner";
import { StatRestButton } from "./StatRestButton";
import { QuestlineList } from "./QuestlineList";
import "./CharacterPanel.css";

// Mirrors app.py's "⚔️ Character" section: Level/Runes metrics, an active
// bloodstain warning, one "Rest" button per stat (bonfire leveling), and
// the nested Questlines subsection. The character itself comes from
// AppDataContext (shared with ArmoryPanel, since a purchase there also
// changes Runes/level); bloodstain and questlines are panel-local fetches,
// nobody else needs them.
//
// Stat order: iterates Object.keys(character.next_costs) rather than a
// hardcoded frontend stat list -- next_costs is built server-side from
// CHARACTER_STATS (config.py) in order, and dict/JSON key order is
// preserved end to end, so this stays in sync with the backend's single
// source of truth without duplicating the stat list here.

export function CharacterPanel() {
  const { character, characterError, refetchCharacter } = useAppData();
  const [bloodstain, setBloodstain] = useState<BloodstainOut | null>(null);
  const [questlines, setQuestlines] = useState<QuestlineOut[] | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [restingStat, setRestingStat] = useState<string | null>(null);
  const [restError, setRestError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      apiGet<BloodstainOut | null>("/character/bloodstain"),
      apiGet<QuestlineOut[]>("/questlines"),
    ])
      .then(([bloodstainData, questlinesData]) => {
        if (cancelled) return;
        setBloodstain(bloodstainData);
        setQuestlines(questlinesData);
      })
      .catch((e: ApiError) => {
        if (!cancelled) setFetchError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleRest(statName: string) {
    setRestingStat(statName);
    setRestError(null);
    try {
      await apiPost<CharacterOut>("/character/rest", { stat_name: statName });
      // Runes/level changed -- refresh the shared character state so
      // ArmoryPanel's can_buy-backing Rune/level data stays live too.
      await refetchCharacter();
    } catch (e) {
      setRestError(e instanceof ApiError ? e.message : "Failed to rest.");
    } finally {
      setRestingStat(null);
    }
  }

  const error = characterError ?? fetchError;

  return (
    <section className="character-panel">
      <h2>⚔️ Character</h2>

      {error && <p className="character-panel__error">{error}</p>}

      {!error && character === null && (
        <p className="character-panel__loading">Loading…</p>
      )}

      {!error && character !== null && (
        <>
          <div className="character-panel__metrics">
            <div className="character-panel__metric">
              <span
                className="character-panel__metric-label"
                title="Sum of all stat levels."
              >
                Level
              </span>
              <span className="character-panel__metric-value">{character.level}</span>
            </div>
            <div className="character-panel__metric">
              <span className="character-panel__metric-label">Runes</span>
              <span className="character-panel__metric-value">{character.runes}</span>
            </div>
          </div>

          <BloodstainBanner bloodstain={bloodstain} />

          <p className="character-panel__caption">
            Bonfire leveling — Runes only convert to a permanent stat level when you
            deliberately rest, never automatically.
          </p>

          {restError && <p className="character-panel__error">{restError}</p>}

          <div className="character-panel__stats">
            {Object.keys(character.next_costs).map((statName) => (
              <StatRestButton
                key={statName}
                statName={statName}
                level={character.stats[statName] ?? 0}
                cost={character.next_costs[statName]}
                runes={character.runes}
                pending={restingStat === statName}
                onRest={() => handleRest(statName)}
              />
            ))}
          </div>

          {questlines !== null && questlines.length > 0 && (
            <QuestlineList questlines={questlines} />
          )}
        </>
      )}
    </section>
  );
}

export default CharacterPanel;
