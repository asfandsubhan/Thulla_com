const createForm = document.querySelector("#createForm");
const joinForm = document.querySelector("#joinForm");
const entry = document.querySelector("#entry");
const game = document.querySelector("#game");
const message = document.querySelector("#message");
const roomTitle = document.querySelector("#roomTitle");
const gameName = document.querySelector("#gameName");
const gameDescription = document.querySelector("#gameDescription");
const playersEl = document.querySelector("#players");
const handEl = document.querySelector("#hand");
const logEl = document.querySelector("#log");
const pileTop = document.querySelector("#pileTop");
const deckCount = document.querySelector("#deckCount");
const turnLabel = document.querySelector("#turnLabel");
const claimLabel = document.querySelector("#claimLabel");
const declaredRank = document.querySelector("#declaredRank");
const playCards = document.querySelector("#playCards");
const drawCard = document.querySelector("#drawCard");
const callBluff = document.querySelector("#callBluff");
const startGame = document.querySelector("#startGame");
const resetRoom = document.querySelector("#resetRoom");
const copyCode = document.querySelector("#copyCode");
const leaveRoom = document.querySelector("#leaveRoom");

const suits = {
  spades: { symbol: "&spades;", red: false },
  hearts: { symbol: "&hearts;", red: true },
  diamonds: { symbol: "&diams;", red: true },
  clubs: { symbol: "&clubs;", red: false },
};

const ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];
let state = {
  code: localStorage.getItem("thullaCode") || "",
  playerId: localStorage.getItem("thullaPlayerId") || "",
  room: null,
  selected: new Set(),
  poll: null,
};

ranks.forEach((rank) => {
  const option = document.createElement("option");
  option.value = rank;
  option.textContent = `Claim ${rank}`;
  declaredRank.appendChild(option);
});

function showMessage(text) {
  message.textContent = text;
  message.classList.toggle("hidden", !text);
  if (text) {
    window.clearTimeout(showMessage.timer);
    showMessage.timer = window.setTimeout(() => message.classList.add("hidden"), 3600);
  }
}

async function api(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Request failed.");
  }
  return data;
}

async function refresh() {
  if (!state.code || !state.playerId) return;
  try {
    const response = await fetch(`/api/state?code=${encodeURIComponent(state.code)}&playerId=${encodeURIComponent(state.playerId)}`);
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 404) {
        returnToHome();
      }
      throw new Error(data.error || "Room not found.");
    }
    state.room = data;
    render();
  } catch (error) {
    showMessage(error.message);
  }
}

function enterRoom(room, playerId) {
  state.room = room;
  state.code = room.code;
  state.playerId = playerId;
  state.selected.clear();
  localStorage.setItem("thullaCode", state.code);
  localStorage.setItem("thullaPlayerId", state.playerId);
  entry.classList.add("hidden");
  game.classList.remove("hidden");
  if (!state.poll) {
    state.poll = window.setInterval(refresh, 1200);
  }
  render();
}

createForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(createForm));
  try {
    const result = await api("/api/create", {
      name: data.name,
      game: data.game,
      maxPlayers: Number(data.maxPlayers),
    });
    enterRoom(result.room, result.playerId);
  } catch (error) {
    showMessage(error.message);
  }
});

joinForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(joinForm));
  try {
    const result = await api("/api/join", {
      name: data.name,
      code: data.code,
    });
    enterRoom(result.room, result.playerId);
  } catch (error) {
    showMessage(error.message);
  }
});

startGame.addEventListener("click", () => roomApi("/api/start", {}));
resetRoom.addEventListener("click", () => roomApi("/api/reset", {}));
drawCard.addEventListener("click", () => roomApi("/api/action", { action: "draw" }));
callBluff.addEventListener("click", () => roomApi("/api/action", { action: "call_bluff" }));
leaveRoom.addEventListener("click", leaveCurrentRoom);

playCards.addEventListener("click", () => {
  roomApi("/api/action", {
    action: "play",
    indexes: [...state.selected],
    declaredRank: declaredRank.value,
  });
});

copyCode.addEventListener("click", async () => {
  if (!state.room) return;
  const text = `Room ${state.room.code} at ${location.origin}`;
  try {
    await navigator.clipboard.writeText(text);
    showMessage("Room code copied.");
  } catch {
    showMessage(text);
  }
});

async function roomApi(path, extra) {
  try {
    const result = await api(path, {
      code: state.code,
      playerId: state.playerId,
      ...extra,
    });
    state.room = result.room;
    state.selected.clear();
    render();
  } catch (error) {
    showMessage(error.message);
  }
}

async function leaveCurrentRoom() {
  if (!state.code || !state.playerId) {
    returnToHome();
    return;
  }

  try {
    await api("/api/leave", {
      code: state.code,
      playerId: state.playerId,
    });
  } catch (error) {
    showMessage(error.message);
  } finally {
    returnToHome();
  }
}

function returnToHome() {
  state.room = null;
  state.code = "";
  state.playerId = "";
  state.selected.clear();
  localStorage.removeItem("thullaCode");
  localStorage.removeItem("thullaPlayerId");
  if (state.poll) {
    window.clearInterval(state.poll);
    state.poll = null;
  }
  game.classList.add("hidden");
  entry.classList.remove("hidden");
}

function render() {
  const room = state.room;
  if (!room) return;
  entry.classList.add("hidden");
  game.classList.remove("hidden");
  roomTitle.textContent = `Room ${room.code}`;
  gameName.textContent = room.gameName;
  gameDescription.textContent = room.description;
  deckCount.textContent = room.deckCount;

  renderPlayers(room);
  renderPile(room);
  renderHand(room);
  renderLog(room);
  renderControls(room);
}

function renderPlayers(room) {
  playersEl.innerHTML = "";
  for (let i = 0; i < room.maxPlayers; i += 1) {
    const player = room.players[i];
    const row = document.createElement("div");
    row.className = "player-row";
    if (!player) {
      row.innerHTML = `<span class="hint">Open seat</span><span class="badge">${i + 1}</span>`;
    } else {
      const host = player.host ? " - host" : "";
      const you = player.id === room.you ? " - you" : "";
      const turn = player.id === room.currentPlayerId ? " turn" : "";
      row.innerHTML = `
        <div>
          <strong class="${turn.trim()}">${escapeHtml(player.name)}</strong>
          <div class="hint">${player.cards} cards - ${player.score} wins${host}${you}</div>
        </div>
        <span class="badge">${player.cards}</span>
      `;
    }
    playersEl.appendChild(row);
  }
}

function renderPile(room) {
  if (room.pileTop) {
    pileTop.className = `card ${suits[room.pileTop.suit].red ? "red-suit" : ""}`;
    pileTop.innerHTML = cardHtml(room.pileTop);
  } else {
    pileTop.className = "card back-card";
    pileTop.innerHTML = `<span>TH</span><small>Pile</small>`;
  }

  const current = room.players.find((player) => player.id === room.currentPlayerId);
  if (room.status === "lobby") {
    turnLabel.textContent = "Lobby";
    claimLabel.textContent = "The host can start once at least two friends have joined.";
  } else if (room.status === "finished") {
    const winner = room.players.find((player) => player.id === room.winner);
    turnLabel.textContent = `${winner ? winner.name : "Someone"} won`;
    claimLabel.textContent = "Host can reset the table for another round.";
  } else {
    turnLabel.textContent = current ? `${current.name}'s turn` : "Playing";
    if (room.lastPlay && room.game === "bluff") {
      claimLabel.textContent = `${room.lastPlay.playerName} claimed ${room.lastPlay.count} card(s) as ${room.lastPlay.declaredRank}.`;
    } else {
      claimLabel.textContent = `${room.pileCount} card(s) in pile. Direction: ${room.direction === 1 ? "clockwise" : "reverse"}.`;
    }
  }
}

function renderHand(room) {
  handEl.innerHTML = "";
  room.hand.forEach((card, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `card ${suits[card.suit].red ? "red-suit" : ""} ${state.selected.has(index) ? "selected" : ""}`;
    button.innerHTML = cardHtml(card);
    button.addEventListener("click", () => {
      if (state.selected.has(index)) {
        state.selected.delete(index);
      } else {
        if (room.game !== "bluff") state.selected.clear();
        state.selected.add(index);
      }
      renderHand(room);
      renderControls(room);
    });
    handEl.appendChild(button);
  });

  if (!room.hand.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = room.status === "playing" ? "No cards in your hand." : "Cards appear after the host starts.";
    handEl.appendChild(empty);
  }
}

function renderLog(room) {
  logEl.innerHTML = "";
  [...room.log].reverse().forEach((item) => {
    const div = document.createElement("div");
    div.className = "log-item";
    div.textContent = item.message;
    logEl.appendChild(div);
  });
}

function renderControls(room) {
  const isHost = room.hostId === state.playerId;
  const isTurn = room.currentPlayerId === state.playerId;
  const playing = room.status === "playing";
  startGame.disabled = !isHost || room.status !== "lobby" || room.players.length < 2;
  resetRoom.disabled = !isHost;
  leaveRoom.textContent = isHost ? "Discard room" : "Back";
  declaredRank.disabled = room.game !== "bluff" || !playing;
  playCards.disabled = !playing || !isTurn || state.selected.size === 0;
  drawCard.disabled = !playing || !isTurn || room.game === "bluff";
  callBluff.disabled = !playing || room.game !== "bluff" || !room.lastPlay?.canChallenge || room.lastPlay.playerId === state.playerId;
}

function cardHtml(card) {
  const suit = suits[card.suit];
  return `
    <span class="card-rank">${card.rank}</span>
    <span class="card-suit">${suit.symbol}</span>
  `;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

if (state.code && state.playerId) {
  refresh();
  state.poll = window.setInterval(refresh, 1200);
}
