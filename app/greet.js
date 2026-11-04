// Greets the agent on the dashboard
function greet(username) {
  const box = document.getElementById("greeting");
  box.textContent = "Welcome back, " + username + "!";   // textContent: the name is never parsed as HTML
}
