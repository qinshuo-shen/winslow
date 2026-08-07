import type { GearOut } from "../../api/types";
import "./GearCard.css";

// Mirrors app.py's per-item row: "**{name}** (lvl {min_level}, {cost}
// Runes)" + " ✅ owned" marker + flavor text caption + a Buy button
// disabled when `!can_buy` (server-computed, not re-derived client-side).
// `pending` additionally disables the button while this item's buy
// request is in flight.

interface GearCardProps {
  item: GearOut;
  pending: boolean;
  onBuy: () => void;
}

export function GearCard({ item, pending, onBuy }: GearCardProps) {
  return (
    <div className="gear-card">
      <div className="gear-card__info">
        <p className="gear-card__name">
          <strong>{item.name}</strong> (lvl {item.min_level}, {item.cost} Runes)
          {item.owned && " ✅ owned"}
        </p>
        <p className="gear-card__flavor">{item.flavor_text}</p>
      </div>
      <button
        type="button"
        className="gear-card__buy"
        disabled={!item.can_buy || pending}
        onClick={onBuy}
      >
        Buy
      </button>
    </div>
  );
}

export default GearCard;
