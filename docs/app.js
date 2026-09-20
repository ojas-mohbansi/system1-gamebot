const distanceEl = document.querySelector('#hero-distance');
const obstacleEl = document.querySelector('#hero-obstacle');
const actionEl = document.querySelector('#hero-action');
const stateEl = document.querySelector('#state-value');
const decisionEl = document.querySelector('#decision-action');
const confidenceEl = document.querySelector('#decision-confidence');
const heroStage = document.querySelector('.hero-stage');

let distance = 100;
let previous = performance.now();

function tick(now) {
  const elapsed = now - previous;
  if (elapsed > 82) {
    distance -= 5;
    if (distance < 5) distance = 100;
    distanceEl.textContent = String(distance).padStart(3, '0');
    obstacleEl.style.top = `${72 + (100 - distance) * 2.28}px`;
    obstacleEl.style.transform = `scale(${1 + (100 - distance) / 150})`;

    const isThreat = distance <= 30;
    const action = isThreat ? 'JUMP' : 'DO_NOTHING';
    actionEl.textContent = `ACTION / ${action}`;
    actionEl.style.color = isThreat ? 'var(--orange)' : 'var(--lime)';
    stateEl.textContent = `Obstacle in Center lane, distance: ${distance} px`;
    decisionEl.textContent = action;
    confidenceEl.textContent = `${isThreat ? '0.950000' : '0.875000'} CONFIDENCE`;
    previous = now;
  }
  requestAnimationFrame(tick);
}

heroStage?.addEventListener('pointermove', (event) => {
  const bounds = heroStage.getBoundingClientRect();
  const x = (event.clientX - bounds.left) / bounds.width - 0.5;
  const y = (event.clientY - bounds.top) / bounds.height - 0.5;
  heroStage.style.transform = `perspective(900px) rotateY(${x * 3}deg) rotateX(${y * -3}deg) rotateZ(1.5deg)`;
});
heroStage?.addEventListener('pointerleave', () => {
  heroStage.style.transform = '';
});

requestAnimationFrame(tick);
