const PASSWORD_HASH = "11d78380af03a111ef3e0607b9b4b2ae7a4d4de17b8c2ea00cf2069b5b565417"; // COPY THIS EXACT STRING TO NETLIFY ENV VAR DASH_KEY_HASH

// Check if already authenticated
if (localStorage.getItem("auth") === "1") {
  window.location.href = "app.html";
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("loginForm");
  const passwordInput = document.getElementById("password");
  const errorMsg = document.getElementById("loginError");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorMsg.style.display = "none";
    const password = passwordInput.value;

    try {
      const buffer = new TextEncoder().encode(password);
      const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      const hashHex = hashArray.map(b => b.toString(16).padStart(2, "0")).join("");

      if (hashHex === PASSWORD_HASH) {
        localStorage.setItem("auth", "1");
        localStorage.setItem("dash_key_hash", hashHex);
        window.location.href = "app.html";
      } else {
        errorMsg.textContent = "Wrong password. Please try again.";
        errorMsg.style.display = "block";
        passwordInput.value = "";
        passwordInput.focus();
      }
    } catch (err) {
      console.error("Authentication error:", err);
      errorMsg.textContent = "Error calculating hash. Please use a modern browser.";
      errorMsg.style.display = "block";
    }
  });
});
