from argparse import ArgumentParser
from .knowledge_graph.cli.training_data_generator_cli import parse_document_and_generate_training_data
from .website_qna.cli.website_qna_generator_cli import parse_website_and_generate_training_data
from loguru import logger


def create_arg_parser():
    parser = ArgumentParser()
    parser.add_argument('choice',type=str,help="enter web for website qna generation and doc for document qna generation")
    parser.add_argument('--generate-training-data', '-g', action='store_const', const='-g', help="Initiate training data generation")
    parser.add_argument('kairon_url', help="Http url to access kairon APIs", action='store')
    parser.add_argument('user', help="Kairon user who is initiating the command", action='store')
    parser.add_argument('token', help="JWT token for the user", action='store')
    return parser


def main():
    parser = create_arg_parser()
    arguments = parser.parse_args()
    logger.debug(arguments.choice)
    logger.debug(arguments.kairon_url)
    logger.debug(arguments.user)
    logger.debug(arguments.token)
    logger.debug("-g: " + arguments.generate_training_data)
    if arguments.choice == "web":
        if arguments.generate_training_data.lower() == '--generate-training-data' or arguments.generate_training_data.lower() == '-g':
            parse_website_and_generate_training_data(arguments.kairon_url, arguments.user, arguments.token)
    elif arguments.choice == "doc":
        if arguments.generate_training_data.lower() == '--generate-training-data' or arguments.generate_training_data.lower() == '-g':
            parse_document_and_generate_training_data(arguments.kairon_url, arguments.user, arguments.token)
    else:
        logger.debug("ERROR: wrong choice as input")

            




if __name__ == "__main__":
    main()
