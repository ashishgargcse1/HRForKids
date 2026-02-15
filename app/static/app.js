function launchConfetti() {
  const colors = ['#ff6b6b', '#4ecdc4', '#ffe66d', '#1a535c', '#ff9f1c'];
  for (let i = 0; i < 90; i++) {
    const dot = document.createElement('div');
    dot.className = 'confetti';
    dot.style.left = Math.random() * 100 + 'vw';
    dot.style.background = colors[Math.floor(Math.random() * colors.length)];
    dot.style.animationDelay = (Math.random() * 0.8) + 's';
    document.body.appendChild(dot);
    setTimeout(() => dot.remove(), 2500);
  }
}
