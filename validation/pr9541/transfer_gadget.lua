function gadget:GetInfo()
	return { name = "PR9541 transfer validation", layer = -100000, enabled = true, handler = true }
end

if not gadgetHandler:IsSyncedCode() then
	local starts = {}
	local highResolution = Spring.GetTimerMicros ~= nil
	local getTimer = highResolution and Spring.GetTimerMicros or Spring.GetTimer
	function gadget:Initialize()
		gadgetHandler.actionHandler.AddSyncAction(gadget, "pr9541_start", function(_, phase, frame)
			starts[phase] = getTimer()
		end)
		gadgetHandler.actionHandler.AddSyncAction(gadget, "pr9541_end", function(_, phase, frame)
			local elapsed = Spring.DiffTimers(getTimer(), starts[phase], true, highResolution)
			Spring.Echo(string.format("PR9541_TIMING phase=%s frame=%d ms=%.6f", phase, frame, elapsed))
		end)
		gadgetHandler.actionHandler.AddSyncAction(gadget, "pr9541_quit", function()
			Spring.Quit()
		end)
	end
	function gadget:GameFrame(frame)
	end
	return
end

local sources, targets = {}, {}
local trackedUnits = {}
local failures = 0

function gadget:UnitPreDamaged(unitID, unitDefID, unitTeam, damage)
	if trackedUnits[unitID] then
		return 0, 0
	end
	return damage, 1
end

function gadget:UnitDestroyed(unitID, unitDefID, unitTeam, attackerID)
	if trackedUnits[unitID] then
		Spring.Echo("PR9541_DESTROYED unit=" .. unitID .. " attacker=" .. tostring(attackerID))
	end
end

local function check(condition, name)
	Spring.Echo("PR9541_CHECK " .. name .. " " .. (condition and "PASS" or "FAIL"))
	if not condition then
		failures = failures + 1
	end
end

local function create(name, count, team, originX, originZ)
	local units = {}
	for index = 1, count do
		local positionX = originX + ((index - 1) % 32) * 24
		local positionZ = originZ + math.floor((index - 1) / 32) * 24
		local unitID = Spring.CreateUnit(name, positionX, Spring.GetGroundHeight(positionX, positionZ), positionZ, 0, team)
		assert(unitID, "could not create " .. name)
		trackedUnits[unitID] = true
		Spring.SetUnitMaxHealth(unitID, 100000000)
		Spring.SetUnitHealth(unitID, 100000000)
		Spring.MoveCtrl.Enable(unitID)
		Spring.GiveOrderToUnit(unitID, CMD.FIRE_STATE, { 0 }, 0)
		Spring.GiveOrderToUnit(unitID, CMD.MOVE_STATE, { 0 }, 0)
		units[index] = unitID
	end
	return units
end

local function assign(firstTarget)
	local remaining = {}
	for index = firstTarget, #targets do
		remaining[#remaining + 1] = targets[index]
	end
	local accepted = Spring.GiveOrderToUnitArray(sources, GameCMD.UNIT_SET_TARGETS, remaining, 0)
	local list = GG.GetUnitTargetList(sources[1])
	local sourceX, sourceY, sourceZ = Spring.GetUnitPosition(sources[1])
	local targetX, targetY, targetZ = Spring.GetUnitPosition(remaining[1])
	Spring.Echo(string.format("PR9541_POS map=%dx%d source=%.1f,%.1f,%.1f target=%.1f,%.1f,%.1f allied=%s ground=%.1f", Game.mapSizeX, Game.mapSizeZ, sourceX, sourceY, sourceZ, targetX, targetY, targetZ, tostring(Spring.AreTeamsAllied(0, 1)), Spring.GetGroundHeight(targetX, targetZ)))
	Spring.Echo("PR9541_ASSIGN accepted=" .. accepted .. " entries=" .. tostring(list and #list) .. " sourceTeam=" .. Spring.GetUnitTeam(sources[1]) .. " targetTeam=" .. Spring.GetUnitTeam(remaining[1]) .. " test=" .. tostring(Spring.GetUnitWeaponTestTarget(sources[1], 1, remaining[1])) .. " command=" .. tostring(Spring.FindUnitCmdDesc(sources[1], GameCMD.UNIT_SET_TARGETS)))
end

function gadget:GameFrame(frame)
	if frame == 1 then
		local targetGadget = assert(gadgetHandler:FindGadget("Target on the move"))
		local remove = {}
		for _, loaded in ipairs(gadgetHandler.gadgets) do
			if loaded ~= targetGadget and loaded ~= gadget then
				remove[#remove + 1] = loaded
			end
		end
		for _, loaded in ipairs(remove) do
			gadgetHandler:RemoveGadget(loaded)
		end
		for _, unitID in ipairs(Spring.GetAllUnits()) do
			Spring.DestroyUnit(unitID, false, true)
		end
		local update = targetGadget.GameFrame
		targetGadget.GameFrame = function(self, updateFrame)
			SendToUnsynced("pr9541_start", "validation", updateFrame)
			update(self, updateFrame)
			SendToUnsynced("pr9541_end", "validation", updateFrame)
		end
	elseif frame == 20 then
		Spring.SetHeightMapFunc(function()
			for positionX = 1000, math.min(4400, Game.mapSizeX), 8 do
				for positionZ = 1000, math.min(2000, Game.mapSizeZ), 8 do
					Spring.SetHeightMap(positionX, positionZ, 100)
				end
			end
		end)
		sources = create("armstump", 128, 0, 1200, 1200)
		targets = create("armnanotc", 768, 1, 3500, 1200)
		Spring.SetUnitSensorRadius(sources[#sources], "los", Game.mapSizeX + Game.mapSizeZ)
	elseif frame == 45 then
		assign(1)
	elseif frame == 50 then
		local listID = GG.GetUnitTargetListID(sources[1])
		for _, unitID in ipairs(sources) do
			local list = GG.GetUnitTargetList(unitID)
			check(list and GG.GetUnitTargetListID(unitID) == listID and #list == 768, "initial_shared_" .. unitID)
		end
	elseif frame == 60 then
		local listID = GG.GetUnitTargetListID(sources[1])
		SendToUnsynced("pr9541_start", "share", frame)
		for index = 1, 256 do
			assert(Spring.TransferUnit(targets[index], 0, true), "target share denied")
		end
		SendToUnsynced("pr9541_end", "share", frame)
		Spring.Echo("PR9541_CALLBACK_REBUILT " .. tostring(GG.GetUnitTargetListID(sources[1]) ~= listID))
	elseif frame == 75 then
		local listID = GG.GetUnitTargetListID(sources[1])
		for _, unitID in ipairs(sources) do
			local list = GG.GetUnitTargetList(unitID)
			check(list and #list == 512 and list[1].target == targets[257] and GG.GetUnitTargetListID(unitID) == listID, "shared_pruned_" .. unitID)
		end
	elseif frame == 80 or frame == 90 then
		local team = frame == 80 and 2 or 0
		SendToUnsynced("pr9541_start", "take", frame)
		for index = 1, 32 do
			assert(Spring.TransferUnit(sources[index], team, false), "source capture denied")
		end
		SendToUnsynced("pr9541_end", "take", frame)
	elseif frame == 100 then
		for index = 1, 32 do
			check(GG.GetUnitTargetList(sources[index]) == nil, "taken_cleared_" .. sources[index])
		end
	elseif frame == 110 then
		assign(257)
	elseif frame == 120 then
		for _, unitID in ipairs(sources) do
			local list = GG.GetUnitTargetList(unitID)
			check(list and #list == 512 and list[1].target == targets[257], "reassigned_" .. unitID)
		end
	elseif frame == 130 then
		SendToUnsynced("pr9541_start", "mass_transfer", frame)
		for index = 257, #targets do
			local success = Spring.TransferUnit(targets[index], 0, true)
			if not success then
				Spring.Echo("PR9541_DENIED team=" .. tostring(Spring.GetUnitTeam(targets[index])) .. " index=" .. index .. " cap=" .. Spring.GetTeamMaxUnits(0) .. " count=" .. Spring.GetTeamUnitCount(0) .. " cheat=" .. tostring(Spring.IsCheatingEnabled()))
			end
			assert(success, "mass transfer denied")
		end
		SendToUnsynced("pr9541_end", "mass_transfer", frame)
	elseif frame == 145 then
		for _, unitID in ipairs(sources) do
			check(GG.GetUnitTargetList(unitID) == nil, "empty_cleared_" .. unitID)
		end
		Spring.Echo("PR9541_RESULT failures=" .. failures)
		SendToUnsynced("pr9541_quit")
	end
end
