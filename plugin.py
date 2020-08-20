#           Yi Hack Plugin
#
#           Author:     galadril, 2020
#
"""
<plugin key="WLANThermo" name="WLANThermo" author="galadril" version="0.0.1" wikilink="https://github.com/galadril/Domoticz-WLANThermo-Plugin" externallink="">
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

class BasePlugin:
    WLANThermoConn = None
    nextConnect = 1
    outstandingPings = 0
    
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
                unitIdMin = int(channel['number'])+100
                unitIdMax = int(channel['number'])+200
                
                temp = int(channel['temp'])
                min = int(channel['min'])
                max = int(channel['max'])
                
                if unitId not in Devices:
                    Domoticz.Device(Name=channel['name'], Unit=unitId, TypeName="Temperature").Create()
                if unitIdMin not in Devices:
                    Domoticz.Device(Name=channel['name']+ " - Min SetPoint", Unit=unitIdMin, Type=242, Subtype=1).Create()
                if unitIdMax not in Devices:
                    Domoticz.Device(Name=channel['name']+ " - Max SetPoint", Unit=unitIdMax, Type=242, Subtype=1).Create()
                
                UpdateDevice(unitId, temp, str(temp), TimedOut=0)
                UpdateDevice(unitIdMin, min, str(min), TimedOut=0)
                UpdateDevice(unitIdMax, max, str(max), TimedOut=0)
            
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
        if Unit > 200:
            channel = Unit - 200
        else:
            if Unit > 100:
                channel = Unit - 100
                setMax = False
        
        postData = '{"number": ' + str(channel) + ', "min": ' + str(Level) + '}'
        if setMax:
            postData = '{"number": ' + str(channel) + ', "max": ' + str(Level) + '}'
        Domoticz.Log("onCommand - Post data: " + str(postData))
        
        self.sendAfterConnect = { 'Verb' : 'POST', 'URL'  : '/setchannels', 'Headers' : {'Authorization': basicAuth, "Accept": "Content-Type: application/json; charset=UTF-8"}, 'Data': postData}
        if (self.WLANThermoConn.Connected() == False):
            Domoticz.Log("onCommand - WLANThermoConn Reconnecting... ")
            self.WLANThermoConn.Connect()
        else:
            Domoticz.Log("onCommand - Still connected to WLANThermo")
            self.WLANThermoConn.Send(self.sendAfterConnect)
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
            self.WLANThermoConn = None
        
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
