function gadget:GetInfo()
 return {name='Replay Parity Observer', desc='Read-only per-frame simulation trace', author='BAR test', layer=-100000, enabled=true}
end
local config=VFS.Include('parity_config.lua')
if gadgetHandler:IsSyncedCode() then
 local observedLists={}
 function gadget:GameFramePost(frame)
  if GG.GetUnitAttackTargetList then
   for _,unitID in ipairs(config.sources or {}) do
    local targets=GG.GetUnitAttackTargetList(unitID)
    if targets and targets~=observedLists[unitID] then
     local ids={};for _,entry in ipairs(targets) do ids[#ids+1]=entry.target end
     SendToUnsynced("parity_controller",frame,unitID,table.concat(ids,","))
    end
    observedLists[unitID]=targets
   end
  end
  if frame<=config.finish and (frame%config.interval==0 or frame==config.finish or (frame>=config.detailStart and frame<=config.detailEnd)) then SendToUnsynced('parity_tick',frame) end
 end
 local function event(kind,...)
  local args={kind,tostring(Spring.GetGameFrame())}
  for i=1,select('#',...) do args[#args+1]=tostring(select(i,...)) end
  SendToUnsynced('parity_event',table.concat(args,'\t'))
 end
 function gadget:UnitDamaged(unitID,unitDefID,team,damage,paralyzer,weaponDefID,projectileID,attackerID)
  event('damage',unitID,damage,paralyzer,weaponDefID,attackerID)
 end
 function gadget:UnitDestroyed(unitID,unitDefID,team,attackerID)
  event('destroyed',unitID,unitDefID,team,attackerID)
 end
 function gadget:UnitCommand(unitID,unitDefID,team,cmdID,params,opts,tag)
  if cmdID==34927 or cmdID==CMD.ATTACK then
   SendToUnsynced('parity_command',Spring.GetGameFrame(),unitID,cmdID,table.concat(params,','),opts.coded or 0)
  end
 end
else
 local trace,commands,hashes,controllers,frametimes,rawEvents
 local previousSim
 local events={}
 local function encode(v)
  if type(v)=='number' then return string.format('%.17g',v) end
  if type(v)=='table' then
   local keys={};for k in pairs(v) do keys[#keys+1]=k end
   table.sort(keys,function(a,b)return tostring(a)<tostring(b)end)
   local s={};for _,k in ipairs(keys) do s[#s+1]=tostring(k)..'='..encode(v[k]) end
   return '{'..table.concat(s,',')..'}'
  end
  return tostring(v)
 end
 local function row(out,kind,id,...)
  local s={kind,tostring(id)}
  for i=1,select('#',...) do s[#s+1]=encode(select(i,...)) end
  out[#out+1]=table.concat(s,'\t')
 end
 local function capture(frame)
  if frame>config.finish then return end
  assert(Spring.GetGameFrame()==frame,"delayed observation")
  local spectator,fullview=Spring.GetSpectatingState()
  assert(spectator and fullview,"observer requires full spectator visibility")
  local out={}
  local units=Spring.GetAllUnits();table.sort(units)
  for _,id in ipairs(units) do
   row(out,'unit',id,Spring.GetUnitDefID(id),Spring.GetUnitTeam(id))
   row(out,'pos',id,Spring.GetUnitPosition(id))
   row(out,'vel',id,Spring.GetUnitVelocity(id))
   row(out,'hp',id,Spring.GetUnitHealth(id))
   row(out,'heading',id,Spring.GetUnitHeading(id))
   row(out,'state',id,Spring.GetUnitStates(id))
   row(out,'xp',id,Spring.GetUnitExperience(id))
   for w=1,#UnitDefs[Spring.GetUnitDefID(id)].weapons do
    row(out,'weapon'..w,id,Spring.GetUnitWeaponTarget(id,w))
    row(out,'reload'..w,id,Spring.GetUnitWeaponState(id,w,'reloadFrame'),Spring.GetUnitWeaponState(id,w,'salvoLeft'),Spring.GetUnitWeaponState(id,w,'nextSalvo'))
   end
  end
  local teams=Spring.GetTeamList();table.sort(teams)
  for _,id in ipairs(teams) do
   row(out,'metal',id,Spring.GetTeamResources(id,'metal'))
   row(out,'energy',id,Spring.GetTeamResources(id,'energy'))
  end
  local features=Spring.GetAllFeatures();table.sort(features)
  for _,id in ipairs(features) do
   row(out,'feature',id,Spring.GetFeatureDefID(id))
   row(out,'featurepos',id,Spring.GetFeaturePosition(id))
   row(out,'featurehp',id,Spring.GetFeatureHealth(id))
   row(out,'featuremetal',id,Spring.GetFeatureResources(id))
  end
  local projectiles=Spring.GetProjectilesInRectangle(-10000,-10000,Game.mapSizeX+10000,Game.mapSizeZ+10000) or {}
  table.sort(projectiles)
  for _,id in ipairs(projectiles) do
   row(out,'projectile',id,Spring.GetProjectileDefID(id),Spring.GetProjectileOwnerID(id))
   row(out,'projectilepos',id,Spring.GetProjectilePosition(id))
   row(out,'projectilevel',id,Spring.GetProjectileVelocity(id))
  end
  local state=table.concat(out,'\n')..'\n'
  hashes:write(frame,'\t',VFS.CalculateHash(state,1),'\t',VFS.CalculateHash(table.concat(events,'\n'),1),'\n');hashes:flush()
  if frame>=config.detailStart and frame<=config.detailEnd and events[1] then
   rawEvents=rawEvents or assert(io.open('events.tsv','w'))
   for _,e in ipairs(events) do rawEvents:write(frame,'\t',e,'\n') end
   rawEvents:flush()
  end
  events={}
  local data=VFS.ZlibCompress(state)
  trace:write('FRAME\t',frame,'\t',#data,'\n',data);trace:flush()
  if frame==0 then Spring.SendCommands({'setmaxspeed 100','setminspeed 100','setspeed 100'}) end
  if frame==config.interval then Spring.Echo('[ReplayParity] SPEED',Spring.GetGameSpeed()) end
  if frame==config.finish then
   trace:write('COMPLETE\t',frame,'\n');trace:flush()
   Spring.Echo('[ReplayParity] COMPLETE '..frame)
   Spring.SendCommands('quitforce')
  end
 end
 function gadget:GameFrame(frame)
  local simTotal=Spring.GetProfilerTimeRecord('Sim',false)
  if previousSim and frametimes and frame<=config.finish then
   local extra=''
   if frame%30==0 then local _,_,_,_,unsyncedKB,_,syncedKB=Spring.GetLuaMemUsage();extra=string.format('%.1f\t%.1f\t%d',syncedKB or -1,unsyncedKB or -1,#Spring.GetAllUnits()) end
   frametimes:write(frame,'\t',string.format('%.6f',simTotal-previousSim),'\t',extra,'\n')
   if frame%300==0 then frametimes:flush() end
  end
  previousSim=simTotal
 end
 function gadget:Initialize()
  frametimes=assert(io.open('frametimes.tsv','w'));frametimes:write('frame\tsim_ms\tsynced_lua_kb\tunsynced_lua_kb\tunits\n')
  trace=assert(io.open('states.bin','wb'));commands=assert(io.open('commands.tsv','w'));hashes=assert(io.open('hashes.tsv','w'));controllers=assert(io.open('controllers.tsv','w'))
  gadgetHandler:AddSyncAction('parity_controller',function(_,frame,unit,targets) controllers:write(frame,'\t',unit,'\t',targets,'\n');controllers:flush() end)
  gadgetHandler:AddSyncAction('parity_event',function(_,text) events[#events+1]=text end)
  gadgetHandler:AddSyncAction('parity_tick',function(_,frame) capture(frame) end)
  gadgetHandler:AddSyncAction('parity_command',function(_,frame,unit,cmd,params,opts)
   commands:write(frame,'\t',unit,'\t',cmd,'\t',params,'\t',opts,'\n');commands:flush()
  end)
 end
 function gadget:Shutdown()
  if frametimes then frametimes:close() end
  if rawEvents then rawEvents:close() end
  if trace then trace:close() end
  if commands then commands:close() end
  if hashes then hashes:close() end
  if controllers then controllers:close() end
 end
end
