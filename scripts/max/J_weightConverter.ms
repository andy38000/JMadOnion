/*
    J_weightConverter.ms - Maya <-> 3ds Max Skin Weight Converter (MaxScript)

    Exports and imports skin weights using a universal JSON format
    for seamless weight transfer between Maya and 3ds Max.

    Usage:
        fileIn @"path\to\J_weightConverter.ms"

    Author: JmadOnion
*/

try(destroyDialog weightConverterRollout) catch()

rollout weightConverterRollout "Maya <-> Max Weight Converter  v1.0" width:480 height:580
(
    -- UI Elements -----------------------------------------------------------

    group "Current Selection  /  当前选择"
    (
        label lblMesh "" align:#left offset:[0,4]
        button btnRefresh "Refresh  刷新" width:100 align:#right
    )

    group "Export  /  导出权重"
    (
        button btnExport "Max -> Maya    导出权重文件" width:440 height:36
    )

    group "Import  /  导入权重"
    (
        button btnImport "Maya -> Max    导入权重文件" width:440 height:36
    )

    group "Bone Mapping  /  骨骼名映射 (可选)"
    (
        button btnLoadMap "Load 加载" width:100 across:4
        button btnSaveMap "Save 保存" width:100
        button btnClearMap "Clear 清除" width:100
        button btnAutoMap "Auto 自动" width:100
        dotNetControl dgvMapping "System.Windows.Forms.DataGridView" \
            width:440 height:140 offset:[0,4]
    )

    group "Log  /  日志"
    (
        dotNetControl txtLog "System.Windows.Forms.TextBox" \
            width:440 height:100
    )

    -- Bone mapping storage
    local boneMapping = #()   -- array of #(srcName, dstName)

    -- Helpers ---------------------------------------------------------------

    fn getSkinMod obj =
    (
        if obj == undefined then return undefined
        for m in obj.modifiers where (classOf m == Skin) do return m
        return undefined
    )

    fn logMsg msg =
    (
        txtLog.AppendText (msg + "\r\n")
    )

    fn escapeJson s =
    (
        local out = ""
        for i = 1 to s.count do
        (
            local c = s[i]
            case c of
            (
                "\"": out += "\\\""
                "\\": out += "\\\\"
                "\n": out += "\\n"
                "\r": out += "\\r"
                "\t": out += "\\t"
                default: out += c
            )
        )
        out
    )

    fn floatToStr val digits:8 =
    (
        local fmt = "%." + (digits as string) + "f"
        formattedPrint val format:fmt
    )

    -- Refresh ---------------------------------------------------------------

    fn refreshSelection =
    (
        if selection.count == 1 then
        (
            local obj = selection[1]
            local skinMod = getSkinMod obj
            if skinMod != undefined then
            (
                try(modPanel.setCurrentObject skinMod) catch()
                local bc = skinOps.getNumberBones skinMod
                local vc = skinOps.getNumberVertices skinMod
                lblMesh.text = obj.name + " | Skin | vtx:" + (vc as string) + \
                    " | bones:" + (bc as string)
            )
            else
            (
                lblMesh.text = obj.name + " (no Skin modifier)"
            )
        )
        else
        (
            lblMesh.text = "Please select one object  请选择一个对象"
        )
    )

    -- Export ----------------------------------------------------------------

    fn exportWeights =
    (
        if selection.count != 1 then
        (
            logMsg "[Error] Please select one skinned object"
            return false
        )

        local obj = selection[1]
        local skinMod = getSkinMod obj
        if skinMod == undefined then
        (
            logMsg "[Error] No Skin modifier found on: " + obj.name
            return false
        )

        local savePath = getSaveFileName caption:"Export Weight File" \
            types:"JSON (*.json)|*.json|All (*.*)|*.*"
        if savePath == undefined then return false

        try(modPanel.setCurrentObject skinMod) catch()

        local t0 = timeStamp()
        local boneCount = skinOps.getNumberBones skinMod
        local vtxCount = skinOps.getNumberVertices skinMod

        logMsg ("[Export] " + obj.name + " vtx:" + (vtxCount as string) + \
            " bones:" + (boneCount as string) + " ...")

        local f = createFile savePath
        if f == undefined then
        (
            logMsg "[Error] Cannot create file: " + savePath
            return false
        )

        format "{\n" to:f
        format "  \"format_version\": \"1.0\",\n" to:f
        format "  \"source_app\": \"max\",\n" to:f
        format "  \"mesh_name\": \"%\",\n" (escapeJson obj.name) to:f
        format "  \"vertex_count\": %,\n" vtxCount to:f

        -- influences
        format "  \"influences\": [" to:f
        for bi = 1 to boneCount do
        (
            local bn = skinOps.getBoneName skinMod bi 0
            format "\"%\"" (escapeJson bn) to:f
            if bi < boneCount then format ", " to:f
        )
        format "],\n" to:f

        -- weights
        format "  \"weights\": [\n" to:f
        for vi = 1 to vtxCount do
        (
            format "    {" to:f
            local wCount = skinOps.getVertexWeightCount skinMod vi
            local firstW = true
            for wi = 1 to wCount do
            (
                local boneID = skinOps.getVertexWeightBoneID skinMod vi wi
                local weight = skinOps.getVertexWeight skinMod vi wi
                if weight > 0.0000001 then
                (
                    local boneName = skinOps.getBoneName skinMod boneID 0
                    if not firstW then format ", " to:f
                    format "\"%\": %" (escapeJson boneName) (floatToStr weight) to:f
                    firstW = false
                )
            )
            format "}" to:f
            if vi < vtxCount then format "," to:f
            format "\n" to:f
        )
        format "  ]\n" to:f
        format "}" to:f

        close f

        local elapsed = (timeStamp() - t0) / 1000.0
        logMsg ("[Success] Exported in " + (floatToStr elapsed digits:2) + \
            "s -> " + savePath)
        return true
    )

    -- Import ----------------------------------------------------------------

    fn parseJsonWeightFile filePath =
    (
        /*
            Lightweight JSON parser for the weight file format.
            Returns a struct-like array:
              #(vertexCount, influenceNames, weightsArray)
            where weightsArray[vtx] = #( #(boneName, weight), ... )
        */

        local f = openFile filePath mode:"r"
        if f == undefined then
            throw ("Cannot open file: " + filePath)

        local content = ""
        while not (eof f) do
            content += (readLine f) + "\n"
        close f

        -- Extract vertex_count
        local vtxCountPattern = "\"vertex_count\"\\s*:\\s*([0-9]+)"
        local vtxCountRx = dotNetObject "System.Text.RegularExpressions.Regex" vtxCountPattern
        local vtxCountMatch = vtxCountRx.Match content
        if not vtxCountMatch.Success then throw "Cannot find vertex_count in file"
        local fileVtxCount = (vtxCountMatch.Groups.Item[1]).Value as integer

        -- Extract influences array
        local infPattern = "\"influences\"\\s*:\\s*\\[([^\\]]+)\\]"
        local infRx = dotNetObject "System.Text.RegularExpressions.Regex" infPattern
        local infMatch = infRx.Match content
        if not infMatch.Success then throw "Cannot find influences in file"
        local infStr = (infMatch.Groups.Item[1]).Value

        local infNames = #()
        local namePattern = "\"([^\"]*)\""
        local nameRx = dotNetObject "System.Text.RegularExpressions.Regex" namePattern
        local nameMatches = nameRx.Matches infStr
        for i = 0 to nameMatches.Count - 1 do
        (
            local m = nameMatches.Item[i]
            append infNames ((m.Groups.Item[1]).Value)
        )

        -- Extract weights array
        local weightsStart = (dotNetObject "System.Text.RegularExpressions.Regex" \
            "\"weights\"\\s*:\\s*\\[").Match content
        if not weightsStart.Success then throw "Cannot find weights in file"

        local wStartIdx = weightsStart.Index + weightsStart.Length

        -- Parse each vertex block { "bone": val, ... }
        local vtxBlockPattern = "\\{([^}]*)\\}"
        local vtxBlockRx = dotNetObject "System.Text.RegularExpressions.Regex" vtxBlockPattern
        local subContent = (dotNetObject "System.String" content).Substring wStartIdx
        local vtxMatches = vtxBlockRx.Matches subContent

        local weightsArray = #()
        for vi = 0 to vtxMatches.Count - 1 do
        (
            local block = (vtxMatches.Item[vi].Groups.Item[1]).Value
            local pairPattern = "\"([^\"]*)\"\\s*:\\s*([0-9eE.+-]+)"
            local pairRx = dotNetObject "System.Text.RegularExpressions.Regex" pairPattern
            local pairs = pairRx.Matches block

            local vtxWeights = #()
            for pi = 0 to pairs.Count - 1 do
            (
                local p = pairs.Item[pi]
                local boneName = (p.Groups.Item[1]).Value
                local weightVal = (p.Groups.Item[2]).Value as float
                if weightVal > 0.0000001 then
                    append vtxWeights #(boneName, weightVal)
            )
            append weightsArray vtxWeights
        )

        #(fileVtxCount, infNames, weightsArray)
    )

    fn importWeights =
    (
        if selection.count != 1 then
        (
            logMsg "[Error] Please select one object with Skin modifier"
            return false
        )

        local obj = selection[1]
        local skinMod = getSkinMod obj
        if skinMod == undefined then
        (
            logMsg "[Error] No Skin modifier found. Add Skin modifier and bones first."
            return false
        )

        local loadPath = getOpenFileName caption:"Import Weight File" \
            types:"JSON (*.json)|*.json|All (*.*)|*.*"
        if loadPath == undefined then return false

        try(modPanel.setCurrentObject skinMod) catch()

        local t0 = timeStamp()
        logMsg ("[Import] " + obj.name + " <- " + loadPath)

        local parsed = undefined
        try
        (
            parsed = parseJsonWeightFile loadPath
        )
        catch
        (
            logMsg ("[Error] Failed to parse file: " + (getCurrentException()))
            return false
        )

        local fileVtxCount = parsed[1]
        local fileInfluences = parsed[2]
        local fileWeights = parsed[3]

        local meshVtxCount = skinOps.getNumberVertices skinMod
        if meshVtxCount != fileVtxCount then
        (
            logMsg ("[Error] Vertex count mismatch: mesh=" + (meshVtxCount as string) + \
                " file=" + (fileVtxCount as string))
            return false
        )

        -- Build bone name -> ID mapping for current Skin modifier
        local maxBoneCount = skinOps.getNumberBones skinMod
        local boneNameToID = dotNetObject "System.Collections.Generic.Dictionary`2[System.String,System.Int32]"
        for bi = 1 to maxBoneCount do
        (
            local bn = skinOps.getBoneName skinMod bi 0
            if not (boneNameToID.ContainsKey bn) then
                boneNameToID.Add bn bi
        )

        -- Apply bone mapping
        local applyMapping = (boneMapping.count > 0)

        local missingBones = #()
        local matchedCount = 0

        -- Set weights vertex by vertex
        for vi = 1 to meshVtxCount do
        (
            local vtxW = fileWeights[vi]
            if vtxW.count == 0 then continue

            local boneIDs = #()
            local weightVals = #()

            for wi = 1 to vtxW.count do
            (
                local boneName = vtxW[wi][1]
                local wVal = vtxW[wi][2]

                -- Apply mapping if available
                if applyMapping then
                (
                    for mi = 1 to boneMapping.count do
                    (
                        if boneMapping[mi][1] == boneName then
                        (
                            boneName = boneMapping[mi][2]
                            exit
                        )
                    )
                )

                if boneNameToID.ContainsKey boneName then
                (
                    append boneIDs (boneNameToID.Item[boneName])
                    append weightVals wVal
                )
                else
                (
                    if (findItem missingBones boneName) == 0 then
                        append missingBones boneName
                )
            )

            if boneIDs.count > 0 then
                skinOps.replaceVertexWeights skinMod vi boneIDs weightVals
        )

        local elapsed = (timeStamp() - t0) / 1000.0
        logMsg ("[Success] Import completed in " + (floatToStr elapsed digits:2) + "s")
        logMsg ("  Vertices: " + (meshVtxCount as string))

        if missingBones.count > 0 then
        (
            local missingStr = ""
            for mb in missingBones do
                missingStr += mb + ", "
            logMsg ("[Warning] Missing bones: " + missingStr)
        )

        return true
    )

    -- Mapping ---------------------------------------------------------------

    fn setupMappingGrid =
    (
        dgvMapping.ColumnCount = 2
        dgvMapping.Columns.Item[0].HeaderText = "Source Bone  源骨骼"
        dgvMapping.Columns.Item[1].HeaderText = "Target Bone  目标骨骼"
        dgvMapping.Columns.Item[0].Width = 200
        dgvMapping.Columns.Item[1].Width = 200
        dgvMapping.AllowUserToAddRows = true
        dgvMapping.AllowUserToDeleteRows = true
        dgvMapping.RowHeadersVisible = false
        dgvMapping.BackgroundColor = (dotNetClass "System.Drawing.Color").FromArgb 50 50 50
        dgvMapping.DefaultCellStyle.BackColor = (dotNetClass "System.Drawing.Color").FromArgb 60 60 60
        dgvMapping.DefaultCellStyle.ForeColor = (dotNetClass "System.Drawing.Color").White
        dgvMapping.GridColor = (dotNetClass "System.Drawing.Color").FromArgb 80 80 80
    )

    fn refreshMappingGrid =
    (
        dgvMapping.Rows.Clear()
        for m in boneMapping do
        (
            dgvMapping.Rows.Add #(m[1], m[2])
        )
    )

    fn readMappingFromGrid =
    (
        boneMapping = #()
        for ri = 0 to dgvMapping.Rows.Count - 2 do
        (
            local row = dgvMapping.Rows.Item[ri]
            local srcCell = row.Cells.Item[0].Value
            local dstCell = row.Cells.Item[1].Value
            if srcCell != undefined and dstCell != undefined then
            (
                local s = srcCell as string
                local d = dstCell as string
                if s != "" and d != "" and s != d then
                    append boneMapping #(s, d)
            )
        )
    )

    fn loadMappingFile =
    (
        local fp = getOpenFileName caption:"Load Bone Mapping" \
            types:"JSON (*.json)|*.json|Text (*.txt)|*.txt"
        if fp == undefined then return()

        local f = openFile fp mode:"r"
        if f == undefined then
        (
            logMsg "[Error] Cannot open mapping file"
            return()
        )

        local content = ""
        while not (eof f) do content += (readLine f) + "\n"
        close f

        boneMapping = #()
        local pairPattern = "\"([^\"]*)\"\\s*:\\s*\"([^\"]*)\""
        local pairRx = dotNetObject "System.Text.RegularExpressions.Regex" pairPattern
        local matches = pairRx.Matches content
        for i = 0 to matches.Count - 1 do
        (
            local m = matches.Item[i]
            local src = (m.Groups.Item[1]).Value
            local dst = (m.Groups.Item[2]).Value
            append boneMapping #(src, dst)
        )

        refreshMappingGrid()
        logMsg ("[Mapping] Loaded " + (boneMapping.count as string) + " entries")
    )

    fn saveMappingFile =
    (
        local fp = getSaveFileName caption:"Save Bone Mapping" \
            types:"JSON (*.json)|*.json"
        if fp == undefined then return()

        readMappingFromGrid()

        local f = createFile fp
        format "{\n" to:f
        for i = 1 to boneMapping.count do
        (
            local m = boneMapping[i]
            format "  \"%\": \"%\"" (escapeJson m[1]) (escapeJson m[2]) to:f
            if i < boneMapping.count then format "," to:f
            format "\n" to:f
        )
        format "}" to:f
        close f

        logMsg ("[Mapping] Saved " + (boneMapping.count as string) + " entries -> " + fp)
    )

    fn autoMapping =
    (
        if selection.count != 1 then
        (
            logMsg "[Error] Please select one skinned object"
            return()
        )

        local skinMod = getSkinMod selection[1]
        if skinMod == undefined then
        (
            logMsg "[Error] No Skin modifier found"
            return()
        )

        try(modPanel.setCurrentObject skinMod) catch()

        boneMapping = #()
        local bc = skinOps.getNumberBones skinMod
        for bi = 1 to bc do
        (
            local bn = skinOps.getBoneName skinMod bi 0
            -- Common auto-mapping: strip "Bip001 " prefix, replace spaces with underscores
            local mapped = bn
            -- Add the original as-is (identity mapping shown for editing)
            append boneMapping #(bn, mapped)
        )

        refreshMappingGrid()
        logMsg ("[Mapping] Listed " + (bc as string) + " bones for manual editing")
    )

    -- Event Handlers --------------------------------------------------------

    on weightConverterRollout open do
    (
        txtLog.Multiline = true
        txtLog.ScrollBars = (dotNetClass "System.Windows.Forms.ScrollBars").Vertical
        txtLog.ReadOnly = true
        txtLog.BackColor = (dotNetClass "System.Drawing.Color").FromArgb 40 40 40
        txtLog.ForeColor = (dotNetClass "System.Drawing.Color").White
        txtLog.Font = dotNetObject "System.Drawing.Font" "Consolas" 9

        setupMappingGrid()
        refreshSelection()
        logMsg "[Ready] Maya <-> Max Weight Converter"
        logMsg "  Export: Select skinned mesh -> click 'Max -> Maya'"
        logMsg "  Import: Select mesh with Skin -> click 'Maya -> Max'"
    )

    on btnRefresh pressed do refreshSelection()
    on btnExport pressed do exportWeights()
    on btnImport pressed do importWeights()
    on btnLoadMap pressed do loadMappingFile()
    on btnSaveMap pressed do saveMappingFile()
    on btnClearMap pressed do
    (
        boneMapping = #()
        dgvMapping.Rows.Clear()
        logMsg "[Mapping] Cleared"
    )
    on btnAutoMap pressed do autoMapping()
)

createDialog weightConverterRollout style:#(#style_titlebar, #style_sysmenu, #style_toolwindow)
