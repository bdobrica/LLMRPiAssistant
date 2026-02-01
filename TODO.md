# TODO List for LLMRPiAssistant

This document tracks planned improvements, bug fixes, and feature additions, with special focus on game development capabilities.

## ✅ Completed Features

### WiFi Provisioning System (January 2026)
- ✅ NetworkManager-based WiFi management
- ✅ Automatic AP fallback when offline
- ✅ Flask web UI for network configuration
- ✅ Multi-network memory (remembers all configured networks)
- ✅ Systemd service integration
- ✅ Makefile installation target
- ✅ Comprehensive documentation

**Implementation Details:**
- Uses NetworkManager for robust WiFi control
- `piwifi-manager.service` monitors connectivity and manages AP mode
- `piwifi-flask.service` provides web UI at http://192.168.4.1:8080
- Remembers unlimited networks via NetworkManager connection profiles
- Automatic reconnection to any known network

## 🚨 Critical Fixes (High Priority)

### 1. Conversation History Management
**Status**: Not Started  
**Priority**: Critical  
**Issue**: Conversation history grows indefinitely, will eventually exceed context window

**Tasks**:
- [ ] Add conversation history limit (e.g., last 10 messages)
- [ ] Implement sliding window for conversation context
- [ ] Add manual conversation reset command (voice or config)
- [ ] Track token usage and warn when approaching limits
- [ ] Consider conversation summarization for long sessions

**Implementation**:
```python
# In openai_client.py
def _trim_conversation_history(self, max_messages=10):
    """Keep only recent messages plus system prompt."""
    if len(self.conversation_history) > max_messages + 1:
        system_prompt = self.conversation_history[0]
        recent = self.conversation_history[-(max_messages):]
        self.conversation_history = [system_prompt] + recent
```

### 2. Missing apa102.py Implementation
**Status**: Not Started  
**Priority**: High  
**Issue**: LED functionality references missing module

**Tasks**:
- [ ] Locate or implement apa102.py SPI driver
- [ ] Test LED functionality end-to-end
- [ ] Add fallback if SPI not available
- [ ] Document LED hardware requirements

### 3. Audio Output Device Configuration
**Status**: Not Started  
**Priority**: High  
**Issue**: Hardcoded `hw:0,0` may not exist on all systems

**Tasks**:
- [ ] Test audio device availability on startup
- [ ] List available ALSA devices if configured device fails
- [ ] Provide device selection wizard
- [ ] Fallback to default device if hw:0,0 unavailable
- [ ] Add text-only mode if no audio output available

## ⚠️ Important Improvements (Medium Priority)

### 4. OpenAI API Error Handling
**Status**: Not Started  
**Priority**: High  

**Tasks**:
- [ ] Add retry logic with exponential backoff
- [ ] Handle rate limiting (429 errors)
- [ ] Handle network timeouts gracefully
- [ ] Add offline mode detection
- [ ] Queue requests during temporary failures
- [ ] User feedback for API errors ("Connection issue, please try again")

### 5. Adaptive Silence Detection
**Status**: Not Started  
**Priority**: Medium  

**Tasks**:
- [ ] Measure ambient noise level on startup
- [ ] Dynamically adjust silence_rms_threshold
- [ ] Add "calibration mode" for noisy environments
- [ ] Support manual threshold adjustment via voice command
- [ ] Log noise levels for debugging

### 6. Wake Word Configuration
**Status**: Not Started  
**Priority**: Medium  

**Tasks**:
- [ ] Document available wake words in config
- [ ] Allow wake word selection in config.ini
- [ ] Support custom wake word models
- [ ] Test all default wake words
- [ ] Add wake word training guide

### 7. Streaming Response Support
**Status**: Not Started  
**Priority**: Medium  

**Tasks**:
- [ ] Use OpenAI streaming API for faster first-word
- [ ] Stream TTS generation in chunks
- [ ] Start speaking while generating rest of response
- [ ] Reduce perceived latency by 50%+

## 🎮 Game Development Features (High Priority for Your Use Case)

### 8. Multi-Player Support
**Status**: Not Started  
**Priority**: Critical for games  

**Tasks**:
- [ ] Voice identification/registration system
- [ ] Player profiles with names and stats
- [ ] Turn tracking and management
- [ ] Separate conversation contexts per player
- [ ] "Current player" indicator
- [ ] Turn timeout and automatic passing

**Suggested Implementation**:
```python
class GameSession:
    def __init__(self, players: list[str]):
        self.players = players
        self.current_player_index = 0
        self.player_contexts = {p: [] for p in players}
        self.scores = {p: 0 for p in players}
    
    def next_turn(self):
        self.current_player_index = (self.current_player_index + 1) % len(self.players)
    
    def current_player(self) -> str:
        return self.players[self.current_player_index]
```

### 9. Hybrid Command System
**Status**: Not Started  
**Priority**: High  

**Tasks**:
- [ ] Local command parser for game actions
- [ ] Pattern matching for common commands:
  - "roll dice" / "roll d20"
  - "check score" / "leaderboard"
  - "start game" / "end game" / "pause"
  - "next turn" / "pass turn"
  - "save game" / "load game"
- [ ] Route to OpenAI only for conversational/creative responses
- [ ] Reduce latency for frequent commands
- [ ] Add command aliases and shortcuts

**Example Commands**:
```python
GAME_COMMANDS = {
    r"roll (?:a )?d(\d+)": lambda m: roll_die(int(m.group(1))),
    r"(check|show) score": lambda m: show_scores(),
    r"next (turn|player)": lambda m: next_turn(),
    r"start (.+) game": lambda m: start_game(m.group(1)),
}
```

### 10. Game State Persistence
**Status**: Not Started  
**Priority**: High  

**Tasks**:
- [ ] Design game state schema (JSON or SQLite)
- [ ] Auto-save game state after each turn
- [ ] Load game state on startup
- [ ] Support multiple saved games
- [ ] Game session management (active/paused/completed)
- [ ] Export game history and statistics

**State Structure**:
```json
{
  "game_type": "trivia",
  "session_id": "uuid",
  "started_at": "2026-01-09T...",
  "players": ["Alice", "Bob", "Charlie"],
  "current_player": 0,
  "scores": {"Alice": 5, "Bob": 3, "Charlie": 7},
  "turn_number": 15,
  "game_data": { /* game-specific state */ }
}
```

### 11. Game Templates
**Status**: Not Started  
**Priority**: High  

**Tasks**:
- [ ] **Trivia Game**
  - Question categories and difficulty
  - Score tracking and buzzer system
  - Time limits per question
  - Daily/weekly challenges
  
- [ ] **Story Adventure Game**
  - AI-generated branching narratives
  - Player choices and consequences
  - Inventory system
  - Save points and checkpoints
  
- [ ] **Word Games**
  - Rhyme challenge (say words that rhyme)
  - Story chain (players continue story)
  - Word association
  - 20 questions
  
- [ ] **Party Games**
  - Would You Rather
  - Two Truths and a Lie
  - Taboo (AI generates words to avoid)
  - Charades with AI judging

### 12. Scoring & Leaderboards
**Status**: Not Started  
**Priority**: Medium  

**Tasks**:
- [ ] Point system with configurable rules
- [ ] Achievements and badges
- [ ] Historical leaderboard (all-time, monthly, weekly)
- [ ] Statistics tracking (games played, win rate, etc.)
- [ ] Voice announcements for achievements
- [ ] Export leaderboard to CSV/PDF

### 13. Low-Latency Mode
**Status**: Not Started  
**Priority**: Medium  

**Tasks**:
- [ ] Response caching for common queries
- [ ] Local LLM integration (llama.cpp, Ollama)
- [ ] Hybrid mode: local for fast, OpenAI for creative
- [ ] Preload game rules and common responses
- [ ] Optimize audio processing pipeline

## 🔧 Code Quality & Testing

### 14. Unit Tests
**Status**: Not Started  
**Priority**: Medium  

**Tasks**:
- [ ] Test audio processing utilities
- [ ] Test configuration loading
- [ ] Mock OpenAI API for testing
- [ ] Test state machine transitions
- [ ] Test error handling paths
- [ ] CI/CD pipeline setup

### 15. Code Improvements
**Status**: Not Started  
**Priority**: Low  

**Tasks**:
- [ ] Extract callback in `__main__.py:on_recording_complete` to method
- [ ] Convert magic numbers to named constants
  - `skip_chunks = 30` → `MODEL_FLUSH_CHUNKS`
  - `resume_listening_at = time.time() + 3.0` → `PROCESSING_DRAIN_SECONDS`
- [ ] Add type hints to Pixels class
- [ ] Comprehensive docstrings for all public APIs
- [ ] Add logging levels for verbose debugging

### 16. Documentation
**Status**: Mostly Complete  
**Priority**: Medium  

**Tasks**:
- [x] Comprehensive README with setup, usage, architecture
- [x] Configuration reference guide
- [x] Troubleshooting section
- [x] WiFi provisioning documentation
- [ ] API documentation (Sphinx or MkDocs)
- [ ] Game development guide
- [ ] Video tutorial for setup
- [ ] Example game implementations
- [ ] Contributing guidelines

## 🚀 Advanced Features

### 17. Config UI via Flask
**Status**: Not Started  
**Priority**: Medium  

**Tasks**:
- [ ] Extend piwifi webapp to include config.ini editor
- [ ] Web UI for editing assistant settings:
  - OpenAI API key and models
  - Wake word threshold
  - Recording parameters
  - TTS voice selection
- [ ] Hot-reload mechanism to apply config changes without restart
- [ ] Signal-based reload (send SIGHUP to rpi-assistant service)
- [ ] Config validation before applying
- [ ] Backup/restore config functionality

**Suggested Implementation:**
```python
# Add to webapp.py
@app.route("/settings")
def settings():
    config = load_config("../config.ini")
    return render_template("settings.html", config=config)

@app.post("/settings/save")
def save_settings():
    # Validate and save config
    # Send reload signal: subprocess.run(["systemctl", "reload", "rpi-assistant"])
```

### 18. Multi-Language Support
**Status**: Not Started  
**Priority**: Low  

**Tasks**:
- [ ] Detect language in transcription
- [ ] Support multiple TTS voices per language
- [ ] Translate responses on-the-fly
- [ ] Language-specific wake words

### 19. Web Dashboard
**Status**: Not Started  
**Priority**: Low  

**Tasks**:
- [ ] Real-time status monitoring
- [ ] Game statistics visualization
- [ ] Configuration UI (see #17)
- [ ] Remote control (start/stop/pause)
- [ ] Live transcription view
- [ ] Conversation history browser

### 20. Skills/Plugins System
**Status**: Not Started  
**Priority**: Low  

**Tasks**:
- [ ] Plugin architecture for extensibility
- [ ] Built-in skills:
  - Timer/alarm
  - Weather
  - Calculator
  - Music control
  - Smart home integration
- [ ] Skill marketplace or registry

### 21. Voice Activity Detection (VAD)
**Status**: Not Started  
**Priority**: Low  

**Tasks**:
- [ ] Replace simple RMS silence detection with ML-based VAD
- [ ] Use WebRTC VAD or Silero VAD
- [ ] Better handling of background noise
- [ ] Reduced false stops during natural pauses

### 22. Conversation Memory
**Status**: Not Started  
**Priority**: Medium  

**Tasks**:
- [ ] Semantic memory (embeddings database)
- [ ] Remember facts across sessions
- [ ] Personalization per user
- [ ] Context from previous games/sessions

## 📊 Monitoring & Analytics

### 23. Performance Metrics
**Status**: Not Started  
**Priority**: Low  

**Tasks**:
- [ ] Track latency metrics (wake-to-response time)
- [ ] API call duration tracking
- [ ] Token usage statistics and cost estimation
- [ ] Audio quality metrics
- [ ] System resource usage

### 24. Error Tracking
**Status**: Not Started  
**Priority**: Medium  

**Tasks**:
- [ ] Structured error logging
- [ ] Error categorization
- [ ] Alert system for critical errors
- [ ] Automatic error reports

## 🎯 Game-Specific Priorities

For your use case (games with friends), focus on these first:

**Phase 1 (MVP for games):**
1. ✅ Working voice assistant (DONE!)
2. Multi-player support (#8)
3. Hybrid command system (#9)
4. Game state persistence (#10)
5. Conversation history management (#1)

**Phase 2 (First playable games):**
6. Trivia game template (#11)
7. Scoring & leaderboards (#12)
8. Audio output fixes (#3)

**Phase 3 (Enhanced gameplay):**
9. Story adventure game (#11)
10. Low-latency mode (#13)
11. API error handling (#4)
12. More game templates (#11)

**Phase 4 (Polish):**
13. Web dashboard (#18)
14. Achievements system (#12)
15. Voice commands for game control (#9)

## 💡 Implementation Tips

### For Multi-Player Games

```python
# Suggested architecture
class GameEngine:
    def __init__(self, game_type: str, players: list[str]):
        self.session = GameSession(game_type, players)
        self.command_parser = CommandParser()
        self.state_manager = StateManager()
        
    def process_voice_input(self, transcription: str, player: str):
        # Try local command first
        if cmd := self.command_parser.parse(transcription):
            return self.execute_command(cmd, player)
        
        # Fall back to OpenAI for conversational responses
        return self.get_ai_response(transcription, player)
```

### For State Persistence

```python
# Auto-save after each turn
def after_turn_hook(self):
    self.state_manager.save(f"games/{self.session.id}.json")

# Load game on startup
def load_game(session_id: str):
    state = StateManager.load(f"games/{session_id}.json")
    return GameEngine.from_state(state)
```

### For Hybrid Commands

```python
# Fast local commands
LOCAL_COMMANDS = {
    "roll": lambda: random.randint(1, 6),
    "score": lambda: get_scores(),
    "next": lambda: next_turn(),
}

# Use OpenAI for:
# - Story generation
# - Trivia question generation
# - Creative responses
# - Judging player answers
```

## 📅 Suggested Timeline

**Week 1-2**: Critical fixes (#1, #2, #3, #4)  
**Week 3-4**: Multi-player support (#8)  
**Week 5-6**: Hybrid commands and game state (#9, #10)  
**Week 7-8**: First game template (Trivia) (#11)  
**Week 9-10**: Scoring system and polish (#12)  
**Week 11-12**: Additional games and testing (#11)  

## 🤝 Contributing

This is YOUR project! Priorities are based on your goals. As you implement features:

- Mark tasks as complete with ✅
- Add new ideas as they come up
- Update priorities based on what's most fun
- Document lessons learned

## 📝 Notes

- Focus on what makes games fun first, optimize later
- Test with friends early and often
- Start simple (1-2 players) before scaling
- Voice interaction is slower than buttons - design accordingly
- Plan for both competitive and cooperative games
- Consider recording sessions for playback/highlights

Good luck building awesome voice-controlled games! 🎮🎙️
