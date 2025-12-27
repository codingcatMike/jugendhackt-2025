document.addEventListener("DOMContentLoaded", () => {
  console.log("DOM loaded. Initializing chat JS...");
  const { chatId, username, recipientId } = window.chatConfig;

  // ------------------- ELEMENTS -------------------
  const chatContainer = document.getElementById("chatContainer");
  const messageInput = document.getElementById("messageInput");
  const mediaInput = document.getElementById("mediaInput");
  const sendBtn = document.getElementById("sendBtn");
  const gifBtn = document.getElementById("gifShopBtn");
  const gifMenu = document.getElementById("gifMenu");
  const fileName = document.getElementById("fileName");
  const errorMsg = document.getElementById("errorMsg");
  const coinCountEl = document.getElementById("coinCount");
  const coinDisplay = document.getElementById("coinDisplay");

  // ------------------- GLOBAL VARIABLES -------------------
  let userCoins = coinCountEl ? parseInt(coinCountEl.textContent || "0") : 0;
  coinDisplay.textContent = userCoins;


  // ------------------- CHAT LIST CLICK -------------------
  document.querySelectorAll(".chat-item").forEach(item => {
    item.addEventListener("click", () => {
      const chatId = item.dataset.chatId;
      if (chatId) window.location.href = `/chat/${chatId}/`;
    });
  });

  // ------------------- WEBSOCKET -------------------
  const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
  const chatSocket = new WebSocket(`${wsScheme}://${window.location.host}/ws/chat/${chatId}/`);

  function scrollToBottom() {
    if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
  }
  setTimeout(scrollToBottom, 100);

  chatSocket.onopen = () => console.log("WebSocket connected");
  chatSocket.onclose = () => console.log("WebSocket closed");

  chatSocket.onmessage = async function(e) {
    try {
      const data = JSON.parse(e.data);
      console.log("WS message received:", data);

      if (data.error) {
        errorMsg.textContent = data.error;
        return;
      }

      if (typeof data.coins !== "undefined") {
        userCoins = parseInt(data.coins);
        coinDisplay.textContent = userCoins;
        if (coinCountEl) coinCountEl.textContent = userCoins;
        return;
      }

      if (!data.sender) return;

      const msgEl = document.createElement("div");
      const isMe = data.sender === username;
      msgEl.className = "message " + (isMe ? "message-right" : "message-left");

      if (data.media) {
        msgEl.innerHTML = `<img src="${data.media}" width="120"><em>${data.sender}</em> <em>(${data.timestamp})</em>`;
      } else {
        let decryptedText = data.encrypted_message;
        const keyForMe = isMe ? data.encrypted_key_sender : data.encrypted_key_recipient;
        if (keyForMe && data.iv) {
          console.log("Decrypting WS message:", { encryptedMessage: data.encrypted_message, keyForMe, iv: data.iv, isMe });
          decryptedText = await decryptMessageAES(data.encrypted_message, keyForMe, data.iv);
        }
        msgEl.dataset.encrypted = data.encrypted_message || "";
        msgEl.dataset.keySender = data.encrypted_key_sender || "";
        msgEl.dataset.keyRecipient = data.encrypted_key_recipient || "";
        msgEl.dataset.iv = data.iv || "";
        msgEl.innerHTML = `<strong>${data.sender}:</strong> <span>${decryptedText}</span> <em>(${data.timestamp})</em>`;
      }

      chatContainer.appendChild(msgEl);
      scrollToBottom();
      errorMsg.textContent = "";
    } catch (err) {
      console.error("WS onmessage parse error:", err);
    }
  };

  // ------------------- ENCRYPTION HELPERS -------------------
  function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    bytes.forEach(b => binary += String.fromCharCode(b));
    return window.btoa(binary);
  }

  function base64ToArrayBuffer(b64) {
    const binary = window.atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes.buffer;
  }

  async function importPublicKey(base64) {
    return crypto.subtle.importKey(
      "spki",
      base64ToArrayBuffer(base64),
      { name: "RSA-OAEP", hash: "SHA-256" },
      true,
      ["encrypt"]
    );
  }

  async function importPrivateKey(base64) {
    return crypto.subtle.importKey(
      "pkcs8",
      base64ToArrayBuffer(base64),
      { name: "RSA-OAEP", hash: "SHA-256" },
      true,
      ["decrypt"]
    );
  }

  async function encryptMessageAES(message) {
    const aesKey = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt"]);
    const encoder = new TextEncoder();
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, aesKey, encoder.encode(message));
    const rawAesKey = await crypto.subtle.exportKey("raw", aesKey);
    return { ciphertext, rawAesKey, iv };
  }

  async function encryptAESKeyRSA(rawAesKey, recipientPublicKey) {
    return crypto.subtle.encrypt({ name: "RSA-OAEP" }, recipientPublicKey, rawAesKey);
  }

  async function decryptMessageAES(cipherTextB64, encryptedKeyB64, ivB64) {
    try {
      const privateKeyB64 = localStorage.getItem("privateKey_" + username);
      if (!privateKeyB64) throw new Error("Private key not found in localStorage");
      const privateKey = await importPrivateKey(privateKeyB64);
      const encryptedKey = base64ToArrayBuffer(encryptedKeyB64);
      const aesKeyRaw = await crypto.subtle.decrypt({ name: "RSA-OAEP" }, privateKey, encryptedKey);
      const aesKey = await crypto.subtle.importKey("raw", aesKeyRaw, { name: "AES-GCM" }, false, ["decrypt"]);
      const iv = base64ToArrayBuffer(ivB64);
      const cipherBytes = base64ToArrayBuffer(cipherTextB64);
      const decrypted = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, aesKey, cipherBytes);
      return new TextDecoder().decode(decrypted);
    } catch (err) {
      console.error("Decrypt error:", err);
      return "[Fehler beim Entschlüsseln]";
    }
  }

  // ------------------- FETCH RECIPIENT PUBLIC KEY -------------------
  async function getRecipientPublicKey() {
    try {
      const res = await fetch(`/api/get-public-key/${recipientId}/`);
      if (!res.ok) throw new Error("Fehler beim Laden der öffentlichen Schlüssel");
      return await res.text();
    } catch (err) {
      console.error(err);
      errorMsg.textContent = "Kann den öffentlichen Schlüssel des Empfängers nicht laden.";
      return null;
    }
  }

  // ------------------- SEND MESSAGE -------------------
  async function sendMessage(message, recipientPublicKeyB64, mediaData = null, isGif = false, price = 0) {
    try {
      let payload = {};
      if (mediaData) {
        payload = { media: mediaData, media_type: isGif ? "gif" : "image", price };
      } else {
        const { ciphertext, rawAesKey, iv } = await encryptMessageAES(message);
        const recipientKey = await importPublicKey(recipientPublicKeyB64);
        const senderPublicKeyB64 = localStorage.getItem("publicKey_" + username);
        const senderKey = await importPublicKey(senderPublicKeyB64);
        const encryptedKeyRecipient = await encryptAESKeyRSA(rawAesKey, recipientKey);
        const encryptedKeySender = await encryptAESKeyRSA(rawAesKey, senderKey);

        payload = {
          encrypted_message: arrayBufferToBase64(ciphertext),
          encrypted_key_recipient: arrayBufferToBase64(encryptedKeyRecipient),
          encrypted_key_sender: arrayBufferToBase64(encryptedKeySender),
          iv: arrayBufferToBase64(iv)
        };
      }

      chatSocket.send(JSON.stringify(payload));
    } catch (err) {
      console.error("Encryption error:", err);
      errorMsg.textContent = "Fehler bei der Verschlüsselung!";
    }
  }

  // ------------------- SEND BUTTON -------------------
  sendBtn.addEventListener("click", async () => {
    const msg = messageInput.value.trim();
    const mediaFile = mediaInput.files[0];
    const recipientPublicKeyB64 = await getRecipientPublicKey();
    if (!recipientPublicKeyB64) return;
    if (!msg && !mediaFile) return;
    errorMsg.textContent = "";

    if (mediaFile) {
      const reader = new FileReader();
      reader.onload = async function() {
        await sendMessage(null, recipientPublicKeyB64, reader.result, false, 0);
        scrollToBottom();
      };
      reader.readAsDataURL(mediaFile);
    } else {
      await sendMessage(msg, recipientPublicKeyB64);
      scrollToBottom();
    }

    messageInput.value = "";
    mediaInput.value = "";
    fileName.textContent = "";
  });

  messageInput.addEventListener("keyup", e => {
    if (e.key === "Enter") sendBtn.click();
  });

  // ------------------- FILE INPUT -------------------
  mediaInput.addEventListener("change", () => {
    fileName.textContent = mediaInput.files.length > 0 ? mediaInput.files[0].name : "";
  });

  // ------------------- GIF SHOP -------------------
  gifBtn.addEventListener("click", async () => {
    if (gifMenu.style.display === "block") { gifMenu.style.display = "none"; return; }

    try {
      const res = await fetch("/api/gifs/");
      if (!res.ok) throw new Error("Fehler beim Laden der GIF-Liste");
      const gifs = await res.json();
      gifMenu.innerHTML = gifs.map(gif => `
        <div class="gif-item" data-url="${gif.url}" data-price="${gif.price}">
          <img src="${gif.url}" alt="${gif.name}"><span class="gif-price">🪙 ${gif.price}</span>
        </div>
      `).join("");
      gifMenu.style.display = "block";

      gifMenu.querySelectorAll(".gif-item").forEach(item => {
        item.addEventListener("click", async () => {
          const price = parseInt(item.dataset.price);
          const url = item.dataset.url;
          if (userCoins < price) { errorMsg.textContent = "Nicht genügend Coins!"; return; }
          errorMsg.textContent = "Sende GIF...";
          gifMenu.style.display = "none";

          try {
            const blobRes = await fetch(url);
            if (!blobRes.ok) throw new Error("Fehler beim Laden des GIFs");
            const blob = await blobRes.blob();
            const reader = new FileReader();
            reader.onload = async function() {
              const recipientPublicKeyB64 = await getRecipientPublicKey();
              if (!recipientPublicKeyB64) return;
              await sendMessage(null, recipientPublicKeyB64, reader.result, true, price);
              errorMsg.textContent = "";
              scrollToBottom();
            };
            reader.readAsDataURL(blob);
          } catch (err) {
            console.error(err);
            errorMsg.textContent = "Fehler beim Laden der GIF-Datei!";
          }
        });
      });

    } catch (err) {
      console.error(err);
      errorMsg.textContent = "Fehler beim Laden der GIFs.";
    }
  });

  // ------------------- KEY GENERATION -------------------
  const generateKeysBtn = document.getElementById("generateKeysBtn");
  generateKeysBtn.addEventListener("click", () => generateAndUploadKeys());

  async function generateAndUploadKeys() {
    const uploadUrl = "/upload_public_key/";
    try {
      const keyPair = await crypto.subtle.generateKey(
        { name: "RSA-OAEP", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
        true, ["encrypt", "decrypt"]
      );
      const publicKeyB64 = arrayBufferToBase64(await crypto.subtle.exportKey("spki", keyPair.publicKey));
      const privateKeyB64 = arrayBufferToBase64(await crypto.subtle.exportKey("pkcs8", keyPair.privateKey));
      localStorage.setItem("privateKey_" + username, privateKeyB64);
      localStorage.setItem("publicKey_" + username, publicKeyB64);

      const res = await fetch(uploadUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
        body: JSON.stringify({ username, chat_id: chatId, public_key: publicKeyB64, algorithm: "RSA-OAEP-2048-SHA256" })
      });
      if (!res.ok) { const text = await res.text(); throw new Error(text); }
      alert("Keys generated & uploaded ✓");
    } catch (err) {
      console.error(err);
      alert("Fehler beim Key-Upload: " + err.message);
    }
  }

  function getCSRFToken() {
    const cookieValue = document.cookie.split("; ").find(row => row.startsWith("csrftoken="));
    return cookieValue ? cookieValue.split("=")[1] : "";
  }

  // ------------------- DECRYPT OLD MESSAGES -------------------
  async function decryptOldMessages() {
    console.log("Decrypting old messages...");
    const messages = Array.from(chatContainer.querySelectorAll(".message")).reverse();
    for (const msgDiv of messages) {
      const msgEl = msgDiv.querySelector("span");
      const isMe = msgDiv.classList.contains("message-right");
      const encryptedMessage = msgDiv.dataset.encrypted;
      const iv = msgDiv.dataset.iv;
      const keyForMe = isMe ? msgDiv.dataset.keySender : msgDiv.dataset.keyRecipient;
      const mediaUrl = msgDiv.dataset.media;

      if (mediaUrl) continue;
      if (!encryptedMessage || !iv || !keyForMe) { msgEl.textContent = "[Fehler beim Entschlüsseln]"; continue; }

      try {
        msgEl.textContent = await decryptMessageAES(encryptedMessage, keyForMe, iv);
      } catch (err) {
        console.error("Decrypt error for old message:", err);
        msgEl.textContent = "[Fehler beim Entschlüsseln]";
      }
    }
  }

  decryptOldMessages();
});
