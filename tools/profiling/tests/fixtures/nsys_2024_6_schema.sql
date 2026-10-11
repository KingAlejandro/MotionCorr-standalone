CREATE TABLE StringIds (
    -- Consolidation of repetitive string values.

    id                          INTEGER   NOT NULL   PRIMARY KEY,      -- ID reference value.
    value                       TEXT      NOT NULL                     -- String value.
);
CREATE TABLE ThreadNames (
    nameId                      INTEGER   NOT NULL,                    -- REFERENCES StringIds(id) -- Thread name
    priority                    INTEGER,                               -- Priority of the thread.
    globalTid                   INTEGER                                -- Serialized GlobalId.
);
CREATE TABLE PROCESSES (
    -- Names and identifiers of processes captured in the report.

    globalPid                   INTEGER,                               -- Serialized GlobalId.
    pid                         INTEGER,                               -- The process ID.
    name                        TEXT                                   -- The process name.
);
CREATE TABLE ANALYSIS_DETAILS (
    -- Details about the analysis session.

    globalVid                   INTEGER   NOT NULL,                    -- Serialized GlobalId.
    duration                    INTEGER   NOT NULL,                    -- The total time span of the entire trace (ns).
    startTime                   INTEGER   NOT NULL,                    -- Trace start timestamp in nanoseconds.
    stopTime                    INTEGER   NOT NULL                     -- Trace stop timestamp in nanoseconds.
);
CREATE TABLE TARGET_INFO_SESSION_START_TIME (
    utcEpochNs                  INTEGER,                               -- UTC Epoch timestamp at start of the capture (ns).
    utcTime                     TEXT,                                  -- Start of the capture in UTC.
    localTime                   TEXT                                   -- Start of the capture in local time of target.
);
CREATE TABLE TARGET_INFO_GPU (
    vmId                        INTEGER   NOT NULL,                    -- Serialized GlobalId.
    id                          INTEGER   NOT NULL,                    -- Device ID.
    name                        TEXT,                                  -- Device name.
    busLocation                 TEXT,                                  -- PCI bus location.
    isDiscrete                  INTEGER,                               -- True if discrete, false if integrated.
    l2CacheSize                 INTEGER,                               -- Size of L2 cache (B).
    totalMemory                 INTEGER,                               -- Total amount of memory on the device (B).
    memoryBandwidth             INTEGER,                               -- Amount of memory transferred (B).
    clockRate                   INTEGER,                               -- Clock frequency (Hz).
    smCount                     INTEGER,                               -- Number of multiprocessors on the device.
    pwGpuId                     INTEGER,                               -- PerfWorks GPU ID.
    uuid                        TEXT,                                  -- Device UUID.
    luid                        INTEGER,                               -- Device LUID.
    chipName                    TEXT,                                  -- Chip name.
    cuDevice                    INTEGER,                               -- CUDA device ID.
    ctxswDevPath                TEXT,                                  -- GPU context switch device node path.
    ctrlDevPath                 TEXT,                                  -- GPU control device node path.
    revision                    INTEGER,                               -- Revision number.
    nodeMask                    INTEGER,                               -- Device node mask.
    constantMemory              INTEGER,                               -- Memory available on device for __constant__ variables (B).
    maxIPC                      INTEGER,                               -- Maximum instructions per count.
    maxRegistersPerBlock        INTEGER,                               -- Maximum number of 32-bit registers available per block.
    maxShmemPerBlock            INTEGER,                               -- Maximum optin shared memory per block.
    maxShmemPerBlockOptin       INTEGER,                               -- Maximum optin shared memory per block.
    maxShmemPerSm               INTEGER,                               -- Maximum shared memory available per multiprocessor (B).
    maxRegistersPerSm           INTEGER,                               -- Maximum number of 32-bit registers available per multiprocessor.
    threadsPerWarp              INTEGER,                               -- Warp size in threads.
    asyncEngines                INTEGER,                               -- Number of asynchronous engines.
    maxWarpsPerSm               INTEGER,                               -- Maximum number of warps per multiprocessor.
    maxBlocksPerSm              INTEGER,                               -- Maximum number of blocks per multiprocessor.
    maxThreadsPerBlock          INTEGER,                               -- Maximum number of threads per block.
    maxBlockDimX                INTEGER,                               -- Maximum X-dimension of a block.
    maxBlockDimY                INTEGER,                               -- Maximum Y-dimension of a block.
    maxBlockDimZ                INTEGER,                               -- Maximum Z-dimension of a block.
    maxGridDimX                 INTEGER,                               -- Maximum X-dimension of a grid.
    maxGridDimY                 INTEGER,                               -- Maximum Y-dimension of a grid.
    maxGridDimZ                 INTEGER,                               -- Maximum Z-dimension of a grid.
    computeMajor                INTEGER,                               -- Major compute capability version number.
    computeMinor                INTEGER,                               -- Minor compute capability version number.
    smMajor                     INTEGER,                               -- Major multiprocessor version number.
    smMinor                     INTEGER                                -- Minor multiprocessor version number.
);
CREATE TABLE TARGET_INFO_SYSTEM_ENV (
    globalVid                   INTEGER,                               -- Serialized GlobalId.
    devStateName                TEXT      NOT NULL,                    -- Device state name.
    name                        TEXT      NOT NULL,                    -- Property name.
    nameEnum                    INTEGER   NOT NULL,                    -- Property enum value.
    value                       TEXT      NOT NULL                     -- Property value.
);
CREATE TABLE META_DATA_EXPORT (
    -- information about nsys export process

    name                        TEXT      NOT NULL,                    -- Name of meta-data record
    value                       TEXT                                   -- Value of meta-data record
);
CREATE TABLE CUPTI_ACTIVITY_KIND_KERNEL (
    start                       INTEGER   NOT NULL,                    -- Event start timestamp (ns).
    end                         INTEGER   NOT NULL,                    -- Event end timestamp (ns).
    deviceId                    INTEGER   NOT NULL,                    -- Device ID.
    contextId                   INTEGER   NOT NULL,                    -- Context ID.
    greenContextId              INTEGER,                               -- Green context ID.
    streamId                    INTEGER   NOT NULL,                    -- Stream ID.
    correlationId               INTEGER,                               -- REFERENCES CUPTI_ACTIVITY_KIND_RUNTIME(correlationId)
    globalPid                   INTEGER,                               -- Serialized GlobalId.
    demangledName               INTEGER   NOT NULL,                    -- REFERENCES StringIds(id) -- Kernel function name w/ templates
    shortName                   INTEGER   NOT NULL,                    -- REFERENCES StringIds(id) -- Base kernel function name
    mangledName                 INTEGER,                               -- REFERENCES StringIds(id) -- Raw C++ mangled kernel function name
    launchType                  INTEGER,                               -- REFERENCES ENUM_CUDA_KERNEL_LAUNCH_TYPE(id)
    cacheConfig                 INTEGER,                               -- REFERENCES ENUM_CUDA_FUNC_CACHE_CONFIG(id)
    registersPerThread          INTEGER   NOT NULL,                    -- Number of registers required for each thread executing the kernel.
    gridX                       INTEGER   NOT NULL,                    -- X-dimension grid size.
    gridY                       INTEGER   NOT NULL,                    -- Y-dimension grid size.
    gridZ                       INTEGER   NOT NULL,                    -- Z-dimension grid size.
    blockX                      INTEGER   NOT NULL,                    -- X-dimension block size.
    blockY                      INTEGER   NOT NULL,                    -- Y-dimension block size.
    blockZ                      INTEGER   NOT NULL,                    -- Z-dimension block size.
    staticSharedMemory          INTEGER   NOT NULL,                    -- Static shared memory allocated for the kernel (B).
    dynamicSharedMemory         INTEGER   NOT NULL,                    -- Dynamic shared memory reserved for the kernel (B).
    localMemoryPerThread        INTEGER   NOT NULL,                    -- Amount of local memory reserved for each thread (B).
    localMemoryTotal            INTEGER   NOT NULL,                    -- Total amount of local memory reserved for the kernel (B).
    gridId                      INTEGER   NOT NULL,                    -- Unique grid ID of the kernel assigned at runtime.
    sharedMemoryExecuted        INTEGER,                               -- Shared memory size set by the driver.
    graphNodeId                 INTEGER,                               -- REFERENCES CUDA_GRAPH_NODE_EVENTS(graphNodeId)
    sharedMemoryLimitConfig     INTEGER                                -- REFERENCES ENUM_CUDA_SHARED_MEM_LIMIT_CONFIG(id)
);
CREATE TABLE CUPTI_ACTIVITY_KIND_MEMCPY (
    start                       INTEGER   NOT NULL,                    -- Event start timestamp (ns).
    end                         INTEGER   NOT NULL,                    -- Event end timestamp (ns).
    deviceId                    INTEGER   NOT NULL,                    -- Device ID.
    contextId                   INTEGER   NOT NULL,                    -- Context ID.
    greenContextId              INTEGER,                               -- Green context ID.
    streamId                    INTEGER   NOT NULL,                    -- Stream ID.
    correlationId               INTEGER,                               -- REFERENCES CUPTI_ACTIVITY_KIND_RUNTIME(correlationId)
    globalPid                   INTEGER,                               -- Serialized GlobalId.
    bytes                       INTEGER   NOT NULL,                    -- Number of bytes transferred (B).
    copyKind                    INTEGER   NOT NULL,                    -- REFERENCES ENUM_CUDA_MEMCPY_OPER(id)
    deprecatedSrcId             INTEGER,                               -- Deprecated, use srcDeviceId instead.
    srcKind                     INTEGER,                               -- REFERENCES ENUM_CUDA_MEM_KIND(id)
    dstKind                     INTEGER,                               -- REFERENCES ENUM_CUDA_MEM_KIND(id)
    srcDeviceId                 INTEGER,                               -- Source device ID.
    srcContextId                INTEGER,                               -- Source context ID.
    dstDeviceId                 INTEGER,                               -- Destination device ID.
    dstContextId                INTEGER,                               -- Destination context ID.
    migrationCause              INTEGER,                               -- REFERENCES ENUM_CUDA_UNIF_MEM_MIGRATION(id)
    graphNodeId                 INTEGER,                               -- REFERENCES CUDA_GRAPH_NODE_EVENTS(graphNodeId)
    virtualAddress              INTEGER                                -- Virtual base address of the page/s being transferred.
);
CREATE TABLE CUPTI_ACTIVITY_KIND_MEMSET (
    start                       INTEGER   NOT NULL,                    -- Event start timestamp (ns).
    end                         INTEGER   NOT NULL,                    -- Event end timestamp (ns).
    deviceId                    INTEGER   NOT NULL,                    -- Device ID.
    contextId                   INTEGER   NOT NULL,                    -- Context ID.
    greenContextId              INTEGER,                               -- Green context ID.
    streamId                    INTEGER   NOT NULL,                    -- Stream ID.
    correlationId               INTEGER,                               -- REFERENCES CUPTI_ACTIVITY_KIND_RUNTIME(correlationId)
    globalPid                   INTEGER,                               -- Serialized GlobalId.
    value                       INTEGER   NOT NULL,                    -- Value assigned to memory.
    bytes                       INTEGER   NOT NULL,                    -- Number of bytes set (B).
    graphNodeId                 INTEGER,                               -- REFERENCES CUDA_GRAPH_NODE_EVENTS(graphNodeId)
    memKind                     INTEGER                                -- REFERENCES ENUM_CUDA_MEM_KIND(id)
);
CREATE TABLE CUPTI_ACTIVITY_KIND_RUNTIME (
    start                       INTEGER   NOT NULL,                    -- Event start timestamp (ns).
    end                         INTEGER   NOT NULL,                    -- Event end timestamp (ns).
    eventClass                  INTEGER   NOT NULL,                    -- REFERENCES ENUM_NSYS_EVENT_CLASS(id)
    globalTid                   INTEGER,                               -- Serialized GlobalId.
    correlationId               INTEGER,                               -- ID used to identify events that this function call has triggered.
    nameId                      INTEGER   NOT NULL,                    -- REFERENCES StringIds(id) -- Function name
    returnValue                 INTEGER   NOT NULL,                    -- Return value of the function call.
    callchainId                 INTEGER                                -- REFERENCES CUDA_CALLCHAINS(id)
);
CREATE TABLE CUPTI_ACTIVITY_KIND_SYNCHRONIZATION (
    start                       INTEGER   NOT NULL,                    -- Event start timestamp (ns).
    end                         INTEGER   NOT NULL,                    -- Event end timestamp (ns).
    deviceId                    INTEGER   NOT NULL,                    -- Device ID.
    contextId                   INTEGER   NOT NULL,                    -- Context ID.
    greenContextId              INTEGER,                               -- Green context ID.
    streamId                    INTEGER   NOT NULL,                    -- Stream ID.
    correlationId               INTEGER,                               -- Correlation ID of the synchronization API to which this result is associated.
    globalPid                   INTEGER,                               -- Serialized GlobalId.
    syncType                    INTEGER   NOT NULL,                    -- REFERENCES ENUM_CUPTI_SYNC_TYPE(id)
    eventId                     INTEGER   NOT NULL                     -- Event ID for which the synchronization API is called.
);
CREATE TABLE CUDA_GPU_MEMORY_USAGE_EVENTS (
    start                       INTEGER   NOT NULL,                    -- Event start timestamp (ns).
    globalPid                   INTEGER   NOT NULL,                    -- Serialized GlobalId.
    deviceId                    INTEGER   NOT NULL,                    -- Device ID.
    contextId                   INTEGER   NOT NULL,                    -- Context ID.
    address                     INTEGER   NOT NULL,                    -- Virtual address of the allocation/deallocation.
    pc                          INTEGER   NOT NULL,                    -- Program counter of the allocation/deallocation.
    bytes                       INTEGER   NOT NULL,                    -- Number of bytes allocated/deallocated (B).
    memKind                     INTEGER   NOT NULL,                    -- REFERENCES ENUM_CUDA_MEM_KIND(id)
    memoryOperationType         INTEGER   NOT NULL,                    -- REFERENCES ENUM_CUDA_DEV_MEM_EVENT_OPER(id)
    name                        TEXT,                                  -- Variable name, if available.
    correlationId               INTEGER,                               -- REFERENCES CUPTI_ACTIVITY_KIND_RUNTIME(correlationId)
    streamId                    INTEGER,                               -- Stream ID.
    localMemoryPoolAddress      INTEGER,                               -- Base address of the local memory pool used
    localMemoryPoolReleaseThreshold   INTEGER,                         -- Release threshold of the local memory pool used
    localMemoryPoolSize         INTEGER,                               -- Size of the local memory pool used
    localMemoryPoolUtilizedSize   INTEGER,                             -- Utilized size of the local memory pool used
    importedMemoryPoolAddress   INTEGER,                               -- Base address of the imported memory pool used
    importedMemoryPoolProcessId   INTEGER                              -- Process ID of the imported memory pool used
);
CREATE TABLE NVTX_EVENTS (
    start                       INTEGER   NOT NULL,                    -- Event start timestamp (ns).
    end                         INTEGER,                               -- Event end timestamp (ns).
    eventType                   INTEGER   NOT NULL,                    -- REFERENCES ENUM_NSYS_EVENT_TYPE(id)
    rangeId                     INTEGER,                               -- Correlation ID returned from a nvtxRangeStart call.
    category                    INTEGER,                               -- User-controlled ID that can be used to group events.
    color                       INTEGER,                               -- Encoded ARGB color value.
    text                        TEXT,                                  -- Explicit name/text (non-registered string)
    globalTid                   INTEGER,                               -- Serialized GlobalId.
    endGlobalTid                INTEGER,                               -- Serialized GlobalId.
    textId                      INTEGER,                               -- REFERENCES StringIds(id) -- Registered NVTX domain/string
    domainId                    INTEGER,                               -- User-controlled ID that can be used to group events.
    uint64Value                 INTEGER,                               -- One of possible payload value union members.
    int64Value                  INTEGER,                               -- One of possible payload value union members.
    doubleValue                 REAL,                                  -- One of possible payload value union members.
    uint32Value                 INTEGER,                               -- One of possible payload value union members.
    int32Value                  INTEGER,                               -- One of possible payload value union members.
    floatValue                  REAL,                                  -- One of possible payload value union members.
    jsonTextId                  INTEGER,                               -- One of possible payload value union members.
    jsonText                    TEXT,                                  -- One of possible payload value union members.
    binaryData                  TEXT                                   -- Binary payload. See docs for format.
);
CREATE TABLE OSRT_API (
    -- OS runtime libraries traced to gather information about low-level userspace APIs.

    start                       INTEGER   NOT NULL,                    -- Event start timestamp (ns).
    end                         INTEGER   NOT NULL,                    -- Event end timestamp (ns).
    eventClass                  INTEGER   NOT NULL,                    -- REFERENCES ENUM_NSYS_EVENT_CLASS(id)
    globalTid                   INTEGER,                               -- Serialized GlobalId.
    nameId                      INTEGER   NOT NULL,                    -- REFERENCES StringIds(id) -- Function name
    returnValue                 INTEGER   NOT NULL,                    -- Return value of the function call.
    nestingLevel                INTEGER,                               -- Zero-base index of the nesting level.
    callchainId                 INTEGER   NOT NULL                     -- REFERENCES OSRT_CALLCHAINS(id)
);
CREATE TABLE ENUM_CUDA_MEMCPY_OPER (
    -- CUDA memcpy operation labels

    id                          INTEGER   NOT NULL   PRIMARY KEY,      -- Enum numerical value.
    name                        TEXT,                                  -- Enum symbol name.
    label                       TEXT                                   -- Enum human name.
);
CREATE TABLE ENUM_CUDA_MEM_KIND (
    -- CUDA memory kind labels

    id                          INTEGER   NOT NULL   PRIMARY KEY,      -- Enum numerical value.
    name                        TEXT,                                  -- Enum symbol name.
    label                       TEXT                                   -- Enum human name.
);
CREATE TABLE ENUM_CUDA_DEV_MEM_EVENT_OPER (
    -- CUDA device mem event operation labels

    id                          INTEGER   NOT NULL   PRIMARY KEY,      -- Enum numerical value.
    name                        TEXT,                                  -- Enum symbol name.
    label                       TEXT                                   -- Enum human name.
);
CREATE TABLE ENUM_CUPTI_SYNC_TYPE (
    -- CUPTI synchronization type labels

    id                          INTEGER   NOT NULL   PRIMARY KEY,      -- Enum numerical value.
    name                        TEXT,                                  -- Enum symbol name.
    label                       TEXT                                   -- Enum human name.
);
CREATE TABLE ENUM_NSYS_EVENT_TYPE (
    -- Nsys event type labels

    id                          INTEGER   NOT NULL   PRIMARY KEY,      -- Enum numerical value.
    name                        TEXT,                                  -- Enum symbol name.
    label                       TEXT                                   -- Enum human name.
);
INSERT INTO ENUM_CUDA_MEMCPY_OPER VALUES(0,'CUDA_MEMCPY_KIND_UNKNOWN','Unknown');
INSERT INTO ENUM_CUDA_MEMCPY_OPER VALUES(1,'CUDA_MEMCPY_KIND_HTOD','Host-to-Device');
INSERT INTO ENUM_CUDA_MEMCPY_OPER VALUES(2,'CUDA_MEMCPY_KIND_DTOH','Device-to-Host');
INSERT INTO ENUM_CUDA_MEMCPY_OPER VALUES(3,'CUDA_MEMCPY_KIND_HTOA','Host-to-Array');
INSERT INTO ENUM_CUDA_MEMCPY_OPER VALUES(4,'CUDA_MEMCPY_KIND_ATOH','Array-to-Host');
INSERT INTO ENUM_CUDA_MEMCPY_OPER VALUES(5,'CUDA_MEMCPY_KIND_ATOA','Array-to-Array');
INSERT INTO ENUM_CUDA_MEMCPY_OPER VALUES(6,'CUDA_MEMCPY_KIND_ATOD','Array-to-Device');
INSERT INTO ENUM_CUDA_MEMCPY_OPER VALUES(7,'CUDA_MEMCPY_KIND_DTOA','Device-to-Array');
INSERT INTO ENUM_CUDA_MEMCPY_OPER VALUES(8,'CUDA_MEMCPY_KIND_DTOD','Device-to-Device');
INSERT INTO ENUM_CUDA_MEMCPY_OPER VALUES(9,'CUDA_MEMCPY_KIND_HTOH','Host-to-Host');
INSERT INTO ENUM_CUDA_MEMCPY_OPER VALUES(10,'CUDA_MEMCPY_KIND_PTOP','Peer-to-Peer');
INSERT INTO ENUM_CUDA_MEMCPY_OPER VALUES(11,'CUDA_MEMCPY_KIND_UVM_HTOD','Unified Host-to-Device');
INSERT INTO ENUM_CUDA_MEMCPY_OPER VALUES(12,'CUDA_MEMCPY_KIND_UVM_DTOH','Unified Device-to-Host');
INSERT INTO ENUM_CUDA_MEMCPY_OPER VALUES(13,'CUDA_MEMCPY_KIND_UVM_DTOD','Unified Device-to-Device');
INSERT INTO ENUM_CUDA_MEM_KIND VALUES(0,'CUDA_MEMOPR_MEMORY_KIND_PAGEABLE','Pageable');
INSERT INTO ENUM_CUDA_MEM_KIND VALUES(1,'CUDA_MEMOPR_MEMORY_KIND_PINNED','Pinned');
INSERT INTO ENUM_CUDA_MEM_KIND VALUES(2,'CUDA_MEMOPR_MEMORY_KIND_DEVICE','Device');
INSERT INTO ENUM_CUDA_MEM_KIND VALUES(3,'CUDA_MEMOPR_MEMORY_KIND_ARRAY','Array');
INSERT INTO ENUM_CUDA_MEM_KIND VALUES(4,'CUDA_MEMOPR_MEMORY_KIND_MANAGED','Managed');
INSERT INTO ENUM_CUDA_MEM_KIND VALUES(5,'CUDA_MEMOPR_MEMORY_KIND_DEVICE_STATIC','Device Static');
INSERT INTO ENUM_CUDA_MEM_KIND VALUES(6,'CUDA_MEMOPR_MEMORY_KIND_MANAGED_STATIC','Managed Static');
INSERT INTO ENUM_CUDA_MEM_KIND VALUES(7,'CUDA_MEMOPR_MEMORY_KIND_UNKNOWN','Unknown');
INSERT INTO ENUM_CUDA_DEV_MEM_EVENT_OPER VALUES(0,'CUDA_DEV_MEM_EVENT_OPR_ALLOCATION','Allocation');
INSERT INTO ENUM_CUDA_DEV_MEM_EVENT_OPER VALUES(1,'CUDA_DEV_MEM_EVENT_OPR_DEALLOCATION','Deallocation');
INSERT INTO ENUM_CUPTI_SYNC_TYPE VALUES(0,'CUPTI_ACTIVITY_SYNCHRONIZATION_TYPE_UNKNOWN','Unknown');
INSERT INTO ENUM_CUPTI_SYNC_TYPE VALUES(1,'CUPTI_ACTIVITY_SYNCHRONIZATION_TYPE_EVENT_SYNCHRONIZE','Event sync');
INSERT INTO ENUM_CUPTI_SYNC_TYPE VALUES(2,'CUPTI_ACTIVITY_SYNCHRONIZATION_TYPE_STREAM_WAIT_EVENT','Stream wait sync');
INSERT INTO ENUM_CUPTI_SYNC_TYPE VALUES(3,'CUPTI_ACTIVITY_SYNCHRONIZATION_TYPE_STREAM_SYNCHRONIZE','Stream sync');
INSERT INTO ENUM_CUPTI_SYNC_TYPE VALUES(4,'CUPTI_ACTIVITY_SYNCHRONIZATION_TYPE_CONTEXT_SYNCHRONIZE','Context sync');
INSERT INTO ENUM_NSYS_EVENT_TYPE VALUES(34,'NvtxMark','NvtxMark');
INSERT INTO ENUM_NSYS_EVENT_TYPE VALUES(59,'NvtxPushPopRange','NvtxPushPopRange');
INSERT INTO ENUM_NSYS_EVENT_TYPE VALUES(60,'NvtxStartEndRange','NvtxStartEndRange');
INSERT INTO META_DATA_EXPORT VALUES('EXPORT_PRODUCT_VERSION','2024.6.2.225');
INSERT INTO META_DATA_EXPORT VALUES('EXPORT_SCHEMA_VERSION','3.16.1');
CREATE TABLE COMPOSITE_EVENTS (
    -- Thread sampling events.

    id                          INTEGER   NOT NULL   PRIMARY KEY,      -- ID of the composite event.
    start                       INTEGER   NOT NULL,                    -- Event start timestamp (ns).
    cpu                         INTEGER,                               -- ID of CPU this thread was running on.
    threadState                 INTEGER,                               -- REFERENCES ENUM_SAMPLING_THREAD_STATE(id)
    globalTid                   INTEGER,                               -- Serialized GlobalId.
    cpuCycles                   INTEGER   NOT NULL                     -- Value of Performance Monitoring Unit (PMU) counter.
);
CREATE TABLE SAMPLING_CALLCHAINS (
    -- Callchain entries obtained from composite events, used to construct function table views.

    id                          INTEGER   NOT NULL,                    -- REFERENCES COMPOSITE_EVENTS(id)
    symbol                      INTEGER   NOT NULL,                    -- REFERENCES StringIds(id) -- Function name
    module                      INTEGER   NOT NULL,                    -- REFERENCES StringIds(id) -- Module name
    kernelMode                  INTEGER,                               -- True if kernel mode.
    thumbCode                   INTEGER,                               -- True if thumb code.
    unresolved                  INTEGER,                               -- True if the symbol was not resolved.
    specialEntry                INTEGER,                               -- True if artifical entry added during processing callchain.
    originalIP                  INTEGER,                               -- Instruction pointer value.
    unwindMethod                INTEGER,                               -- REFERENCES ENUM_STACK_UNWIND_METHOD(id)
    stackDepth                  INTEGER   NOT NULL,                    -- Zero-base index of the given function in call stack.

    PRIMARY KEY (id, stackDepth)
);
CREATE TABLE ENUM_SAMPLING_THREAD_STATE (
    -- Sampling thread state labels

    id                          INTEGER   NOT NULL   PRIMARY KEY,      -- Enum numerical value.
    name                        TEXT,                                  -- Enum symbol name.
    label                       TEXT                                   -- Enum human name.
);
INSERT INTO ENUM_SAMPLING_THREAD_STATE VALUES(0,'Unknown','Unknown');
INSERT INTO ENUM_SAMPLING_THREAD_STATE VALUES(1,'Running','Running');
INSERT INTO ENUM_SAMPLING_THREAD_STATE VALUES(2,'Interruptible','Interruptible');
INSERT INTO ENUM_SAMPLING_THREAD_STATE VALUES(3,'Uninterruptible','Uninterruptible');
INSERT INTO ENUM_SAMPLING_THREAD_STATE VALUES(4,'Stopped','Stopped');
INSERT INTO ENUM_SAMPLING_THREAD_STATE VALUES(5,'Terminated','Terminated');
INSERT INTO ENUM_SAMPLING_THREAD_STATE VALUES(6,'Unscheduled','Unscheduled');
INSERT INTO ENUM_SAMPLING_THREAD_STATE VALUES(7,'Waiting','Waiting');
INSERT INTO ENUM_SAMPLING_THREAD_STATE VALUES(8,'OSRuntime','OS runtime');
INSERT INTO ENUM_SAMPLING_THREAD_STATE VALUES(9,'Initialized','Initialized');
INSERT INTO ENUM_SAMPLING_THREAD_STATE VALUES(10,'Transition','Transition');
