local function runMassSelfD(alliedTeams)
	local timers = { 5, 5 }
	local activePlayers = 0
	local frame = 1
	local messages = {}
	local env = {
		gadget = {},
		gadgetHandler = {
			IsSyncedCode = function()
				return true
			end,
		},
		BAR = {
			Utilities = {
				Gametype = {
					IsSinglePlayer = function()
						return false
					end,
				},
			},
		},
		CMD = { SELFD = 65 },
		SendToUnsynced = function(message)
			messages[#messages + 1] = message
		end,
		Spring = {
			GetGaiaTeamID = function()
				return 99
			end,
			GetTeamAllyTeamID = function(teamID)
				return teamID == 3 and 1 or teamID
			end,
			GetAllyTeamList = function()
				return { 1, 2, 99 }
			end,
			GetTeamList = function(allyTeamID)
				return allyTeamID == 1 and alliedTeams or { allyTeamID }
			end,
			GetTeamInfo = function(teamID)
				return teamID, 0, false, false
			end,
			GetTeamLuaAI = function()
				return ""
			end,
			GetTeamRulesParam = function()
				return activePlayers
			end,
			GetTeamUnits = function()
				return { 1, 2 }
			end,
			GetUnitSelfDTime = function(unitID)
				return timers[unitID]
			end,
			GiveOrderToUnit = function(unitID, cmdID)
				assert.equals(65, cmdID)
				timers[unitID] = 0
			end,
			GetPlayerList = function()
				return { 1 }
			end,
			GetPlayerInfo = function()
				return "player", true, false, 1
			end,
		},
	}
	setmetatable(env, { __index = _G })
	local chunk = assert(loadfile("luarules/gadgets/game_selfd_resign.lua"))
	setfenv(chunk, env)
	chunk()

	return function(active)
		activePlayers = active
		for unitID = 1, 2 do
			assert(env.gadget:AllowCommand(unitID, 1, 1, env.CMD.SELFD))
			timers[unitID] = 5
		end
		env.gadget:GameFrame(frame)
		frame = frame + 15
		return timers
	end, messages
end

describe("mass self-destruct", function()
	it("lets both countdowns run on the first attempt in a duel", function()
		local attempt, messages = runMassSelfD({ 1 })
		assert.same({ 5, 5 }, attempt(1))
		assert.same({}, messages)
	end)

	it("starts counting attempts only when a teammate is active", function()
		local attempt, messages = runMassSelfD({ 1, 3 })
		assert.same({ 5, 5 }, attempt(0))
		assert.same({}, messages)
		assert.same({ 0, 0 }, attempt(1))
		assert.same({ 0, 0 }, attempt(1))
		assert.same({ 5, 5 }, attempt(1))
		assert.same({ 5, 5 }, attempt(1))
		assert.same({ "selfdPolicyWarn", "selfdPolicyWarn", "selfdMassAnalytics" }, messages)
	end)
end)
