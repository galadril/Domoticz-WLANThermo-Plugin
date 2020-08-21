#           Yi Hack Plugin
#
#           Author:     galadril, 2020
#
"""
<plugin key="WLANThermo" name="WLANThermo" author="galadril" version="0.0.2" wikilink="https://github.com/galadril/Domoticz-WLANThermo-Plugin" externallink="">
    <description>
        <h2>WLANThermo Plugin</h2><br/>
        <h3>Features</h3>
        <ul style="list-style-type:square">
            <li>Shows all the channels of WLANThermo within Domoticz</li>
        </ul>
        <h3>Devices</h3>
        <ul style="list-style-type:square">
            <li>Channel, Current Temperatures</li>
            <li>Channel, SetPoint for Min Temperature</li>
            <li>Channel, SetPoint for Max Temperature</li>
            <li>Pitmaster, Percentage of fan speed</li>
            <li>Pitmaster, Set mode (off/auto/manual)</li>
        </ul>
    </description>
    <params>
        <param field="Address" label="IP Address" width="200px" required="true" default="0.0.0.0"/>
        <param field="Username" label="Username" width="200px" required="false" default="admin"/>
        <param field="Password" label="Password" width="200px" required="false" default="admin"/>
        <param field="Mode6" label="Debug" width="200px">
            <options>
                <option label="None" value="0"  default="true" />
                <option label="Python Only" value="2"/>
                <option label="Basic Debugging" value="62"/>
                <option label="Basic + Messages" value="126"/>
                <option label="Connections Only" value="16"/>
                <option label="Connections + Queue" value="144"/>
                <option label="All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
import sys
import json
import base64
import requests

class BasePlugin:
    WLANThermoConn = None
    nextConnect = 1
    outstandingPings = 0
    unitIdPitmaster = 200
    pitmasterState = None
    
    sendData = { 'Verb' : 'GET', 'URL'  : '/data'}
    sendAfterConnect = { 'Verb' : 'GET', 'URL'  : '/data'}
    
    encoded_credentials = ''
    basicAuth = ''
        
    def onStart(self):
        if Parameters["Mode6"] != "0":
            Domoticz.Debugging(int(Parameters["Mode6"]))
            DumpConfigToLog()
        
        sendData = { 'Verb' : 'GET', 'URL'  : '/data'}
        sendAfterConnect = sendData
        
        self.WLANThermoConn = Domoticz.Connection(Name="WLANThermoConn", Transport="TCP/IP", Protocol="HTTP", Address=Parameters["Address"], Port="80")
        self.WLANThermoConn.Connect()
            
        Domoticz.Heartbeat(10)
        return True
        
    def onConnect(self, Connection, Status, Description):
        if (Status == 0):
            Domoticz.Log("Connected successfully to: "+Connection.Address+":"+Connection.Port)
            self.WLANThermoConn.Send(self.sendAfterConnect)
        else:
            Domoticz.Log("Failed to connect ("+str(Status)+") to: "+Connection.Address+":"+Connection.Port)
            Domoticz.Debug("Failed to connect ("+str(Status)+") to: "+Connection.Address+":"+Connection.Port+" with error: "+Description)
            for Key in Devices:
                UpdateDevice(Key, 0, Devices[Key].sValue, 1)
        return True

    def onMessage(self, Connection, Data):
        Response = json.loads(Data["Data"])
        DumpJSONResponseToLog(Response)
        
        for channel in Response["channel"]:
            if channel['temp'] < 999.0:
                Domoticz.Log("Receive new temperature for channel: " + str(channel['name']) + " | " +  str(channel['temp']) )
                
                unitId = int(channel['number'])
                unitIdMin = int(channel['number'])+50
                unitIdMax = int(channel['number'])+100
                
                temp = channel['temp']
                min = channel['min']
                max = channel['max']
                
                if unitId not in Devices:
                    Domoticz.Device(Name=channel['name'], Unit=unitId, TypeName="Temperature").Create()
                if unitIdMin not in Devices:
                    Domoticz.Device(Name=channel['name']+ " - Min SetPoint", Unit=unitIdMin, Type=242, Subtype=1).Create()
                if unitIdMax not in Devices:
                    Domoticz.Device(Name=channel['name']+ " - Max SetPoint", Unit=unitIdMax, Type=242, Subtype=1).Create()
                
                UpdateTemperatureDevice(unitId, str(temp), TimedOut=0)
                UpdateTemperatureDevice(unitIdMin, str(min), TimedOut=0)
                UpdateTemperatureDevice(unitIdMax, str(max), TimedOut=0)
                
        pitValue = Response["pitmaster"]["pm"][0]["value"]
        pitType = Response["pitmaster"]["pm"][0]["typ"]
        pitId = Response["pitmaster"]["pm"][0]["id"]
        self.pitmasterState = Response["pitmaster"]["pm"]
        
        if 249 not in Devices:
            Domoticz.Device(Name="Pitmaster - Value", Unit=249, TypeName="Percentage").Create()
        if (self.unitIdPitmaster+pitId) not in Devices:
            Domoticz.Device(Name="Pitmaster - Mode",  Unit=self.unitIdPitmaster+pitId, TypeName="Selector Switch", Options={"LevelActions": "0|10|20", "LevelNames": "Off|Manual|Auto", "LevelOffHidden": "false"}).Create()

        Domoticz.Log("Receive new pitmaster values: " + str(pitValue) + " | " +  pitType)
        UpdateDevice(249, pitValue, str(pitValue), 0)
        
        if (pitType == 'off'):
            UpdateDevice(self.unitIdPitmaster+pitId, 0, 'Off', 0)
        elif (pitType == 'manual'):
            UpdateDevice(self.unitIdPitmaster+pitId, 10, 'Manual', 0)
        else:
            UpdateDevice(self.unitIdPitmaster+pitId, 20, 'Auto', 0)
        return True

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Log("onCommand - Called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level) + ", Connected: " + str(self.WLANThermoConn.Connected()))

        Command = Command.strip()
        action, sep, params = Command.partition(' ')
        action = action.capitalize()
            
        credentials = ('%s:%s' % (Parameters["Username"], Parameters["Password"]))
        encoded_credentials = base64.b64encode(credentials.encode('ascii'))
        basicAuth = 'Basic %s' % encoded_credentials.decode("ascii")
        
        setMax = True
        channel = Unit
        if Unit > 100:
            channel = Unit - 100
        else:
            if Unit > 50:
                channel = Unit - 50
                setMax = False
        
        if Unit < 200:
            url = "http://" + Parameters["Address"] + "/setchannels"
            data = {"number": channel, "min": Level}
            if setMax:
                data = {"number": channel, "max": Level}
            Domoticz.Log("onCommand - Post data: " + str(data) + " | to url: " + url)
            headers = {'Authorization': basicAuth, 'Content-type': 'application/json', 'Accept': 'text/plain'}
            r = requests.post(url, data=json.dumps(data), headers=headers)
        else:
            mode = "off"
            if (Level == 10):
                mode = "manual"
            elif (Level == 20):
                mode = "auto"
            url = "http://" + Parameters["Address"] + "/setpitmaster"
            self.pitmasterState[0]["typ"] = mode
            Domoticz.Log("onCommand - Post data: " + str(self.pitmasterState) + " | to url: " + url)
            headers = {'Authorization': basicAuth, 'Content-type': 'application/json', 'Accept': 'text/plain'}
            r = requests.post(url, data=json.dumps(self.pitmasterState), headers=headers)
        return True

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Log("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)
        return

    def onHeartbeat(self):
        try:
            if (self.WLANThermoConn.Connected()):
                if (self.outstandingPings > 3):
                    self.WLANThermoConn.Disconnect()
                    self.nextConnect = 0
                else:
                    self.WLANThermoConn.Send(self.sendData)
                    self.outstandingPings = self.outstandingPings + 1
            else:
                # if not connected try and reconnected every 3 heartbeats
                self.outstandingPings = 0
                self.nextConnect = self.nextConnect - 1
                self.sendAfterConnect = self.sendData
                if (self.nextConnect <= 0):
                    self.nextConnect = 1
                    self.WLANThermoConn.Connect()
            return True
        except:
            Domoticz.Log("Unhandled exception in onHeartbeat, forcing disconnect.")
            self.onDisconnect(self.WLANThermoConn)
        
    def onDisconnect(self, Connection):
        Domoticz.Log("Device has disconnected")
        return

    def onStop(self):
        Domoticz.Log("onStop called")
        return True

    def TurnOn(self):
        self.WLANThermoConn.Send(self.sendOnAction)
        return

    def TurnOff(self):
        self.WLANThermoConn.Send(self.sendOffAction)
        return

    def ClearDevices(self):
        # Stop everything and make sure things are synced
        self.cameraState = 0
        self.SyncDevices(0)
        return
        
global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

# Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Settings count: " + str(len(Settings)))
    for x in Settings:
        Domoticz.Debug( "'" + x + "':'" + str(Settings[x]) + "'")
    for x in Images:
        Domoticz.Debug( "'" + x + "':'" + str(Images[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return

def DumpJSONResponseToLog(jsonDict):
    if isinstance(jsonDict, dict):
        Domoticz.Log("JSON Response Details ("+str(len(jsonDict))+"):")
        for x in jsonDict:
            if isinstance(jsonDict[x], dict):
                Domoticz.Log("--->'"+x+" ("+str(len(jsonDict[x]))+"):")
                for y in jsonDict[x]:
                    Domoticz.Log("------->'" + y + "':'" + str(jsonDict[x][y]) + "'")
            else:
                Domoticz.Log("--->'" + x + "':'" + str(jsonDict[x]) + "'")

def UpdateTemperatureDevice(Unit, sValue, TimedOut):
    # Make sure that the Domoticz device still exists (they can be deleted) before updating it 
    if (Unit in Devices):
        if (Devices[Unit].sValue != sValue) or (Devices[Unit].TimedOut != TimedOut):
            Devices[Unit].Update(nValue=0, sValue=str(sValue), TimedOut=TimedOut)
            Domoticz.Log("Update:'"+str(sValue)+"' ("+Devices[Unit].Name+")")
    return

def UpdateDevice(Unit, nValue, sValue, TimedOut):
    # Make sure that the Domoticz device still exists (they can be deleted) before updating it 
    if (Unit in Devices):
        if (Devices[Unit].nValue != nValue) or (Devices[Unit].sValue != sValue) or (Devices[Unit].TimedOut != TimedOut):
            Devices[Unit].Update(nValue=nValue, sValue=str(sValue), TimedOut=TimedOut)
            Domoticz.Log("Update "+str(nValue)+":'"+str(sValue)+"' ("+Devices[Unit].Name+")")
    return

# Synchronise images to match parameter in hardware page
def UpdateImage(Unit):
    if (Unit in Devices) and (Parameters["Mode1"] in Images):
        Domoticz.Debug("Device Image update: '" + Parameters["Mode1"] + "', Currently "+str(Devices[Unit].Image)+", should be "+str( Images[Parameters["Mode1"]].ID))
        if (Devices[Unit].Image != Images[Parameters["Mode1"]].ID):
            Devices[Unit].Update(nValue=Devices[Unit].nValue, sValue=str(Devices[Unit].sValue), Image=Images[Parameters["Mode1"]].ID)
    return
