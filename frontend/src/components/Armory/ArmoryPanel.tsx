import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost, ApiError } from "../../api/client";
import type { GearOut } from "../../api/types";
import { useAppData } from "../../context/AppDataContext";
import { GearCard } from "./GearCard";
import "./ArmoryPanel.css";

// Mirrors app.py's "🛡️ Armory" section: the full gear catalog, each item
// showing name/level/cost/flavor text/owned marker, with a Buy button
// disabled when the server's `can_buy` flag says so -- trusted as-is, not
// re-derived here (the API already replicates app.py's exact can_buy
// formula, see api/routers/gear.py). A successful purchase refetches both
// gear (new owned/can_buy state) and the shared character (Runes spent),
// via AppDataContext's refetchCharacter, so CharacterPanel stays in sync
// too.

export function ArmoryPanel() {
  const { refetchCharacter } = useAppData();
  const [gearList, setGearList] = useState<GearOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [buyingId, setBuyingId] = useState<string | null>(null);
  const [buyError, setBuyError] = useState<string | null>(null);

  const fetchGear = useCallback(async () => {
    try {
      const data = await apiGet<GearOut[]>("/gear");
      setGearList(data);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load gear.");
    }
  }, []);

  useEffect(() => {
    fetchGear();
  }, [fetchGear]);

  async function handleBuy(gearId: string) {
    setBuyingId(gearId);
    setBuyError(null);
    try {
      const data = await apiPost<GearOut[]>(`/gear/${encodeURIComponent(gearId)}/buy`);
      setGearList(data);
      await refetchCharacter();
    } catch (e) {
      setBuyError(e instanceof ApiError ? e.message : "Failed to buy gear.");
    } finally {
      setBuyingId(null);
    }
  }

  return (
    <section className="armory-panel">
      <h2>🛡️ Armory</h2>

      {error && <p className="armory-panel__error">{error}</p>}

      {!error && gearList === null && <p className="armory-panel__loading">Loading…</p>}

      {buyError && <p className="armory-panel__error">{buyError}</p>}

      {!error && gearList !== null && (
        <div className="armory-panel__list">
          {gearList.map((item) => (
            <GearCard
              key={item.gear_id}
              item={item}
              pending={buyingId === item.gear_id}
              onBuy={() => handleBuy(item.gear_id)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export default ArmoryPanel;
