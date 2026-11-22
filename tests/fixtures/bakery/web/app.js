// Storefront entry point.
import { addToCart, cartTotal } from "./cart.js";

export function init() {
  document.querySelectorAll("[data-add]").forEach((btn) => {
    btn.addEventListener("click", () => addToCart(btn.dataset.add));
  });
  return cartTotal();
}
