// Cart state kept in memory.
const lines = [];

export function addToCart(id) {
  lines.push(id);
}

export function cartTotal() {
  return lines.length;
}
