import argparse
from cloudvolume import Vec
from omegaconf import OmegaConf
import igneous.task_creation as tc
from taskqueue import LocalTaskQueue
from utils import DotDict


def main(conf):
    tq = LocalTaskQueue(parallel=conf.n_jobs_skeletonize)

    layer = f"file://{conf.data.output_layer}"
    skeletonize_tasks = tc.create_skeletonizing_tasks(layer, **conf.skeletonize)
    tq.insert(skeletonize_tasks)
    tq.execute()

    merge_tasks = tc.create_unsharded_skeleton_merge_tasks(
        layer, **conf.skeletonize_merge
    )
    tq.insert(merge_tasks)
    tq.execute()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--config",
        action="append",
        help="List of configuration files.",
        required=True,
    )

    args = parser.parse_args()
    print(args.config)

    confs = [OmegaConf.load(c) for c in args.config]
    conf = OmegaConf.merge(*confs)

    # cast to dictionary, because hash of OmegaConf fields depend on greater object
    conf = OmegaConf.to_container(conf, resolve=True)
    assert isinstance(conf, dict), "conf must be a dictionary"
    # allow dot access
    conf = DotDict(conf)

    main(conf)