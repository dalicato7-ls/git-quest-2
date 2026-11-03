document.getElementById("login").addEventListener("submit", (e) => {
  e.preventDefault();
  const agent = e.target.agent.value.trim();
  greet(agent);
});
